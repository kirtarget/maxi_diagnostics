import ipaddress
import os
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_LOCAL_MINIAPP_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")
_NUMERIC_HOST_COMPONENT = re.compile(r"(?:[0-9]+|0x[0-9a-f]+)\Z")
_UNSAFE_HOST_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp", "Zs"})
_IDNA_DOT_EQUIVALENTS = frozenset({".", "\u3002", "\uff0e", "\uff61"})
_BOT_TOKEN = re.compile(r"[0-9]{5,12}:[A-Za-z0-9_-]{8,64}\Z")
_APPLICATION_SECRET = re.compile(r"[A-Za-z0-9_-]{32,128}\Z")
_APPLICATION_SECRET_PLACEHOLDERS = frozenset({
    "test-only-application-secret-1234567890",
    "change-me-application-secret-1234567890",
})


def _contains_unsafe_host_character(value: str) -> bool:
    return any(
        character.isspace()
        or unicodedata.category(character) in _UNSAFE_HOST_CATEGORIES
        for character in value
    )


def _numeric_host_skeleton(hostname: str) -> str:
    normalized = unicodedata.normalize("NFKC", hostname)
    characters: list[str] = []
    for character in normalized:
        if character in _IDNA_DOT_EQUIVALENTS:
            characters.append(".")
            continue
        try:
            characters.append(str(unicodedata.decimal(character)))
        except (TypeError, ValueError):
            characters.append(character.lower())
    return "".join(characters)


def _looks_like_legacy_ipv4(hostname: str) -> bool:
    components = _numeric_host_skeleton(hostname).split(".")
    return bool(components) and all(
        component and _NUMERIC_HOST_COMPONENT.fullmatch(component)
        for component in components
    )


def _validate_miniapp_hostname(hostname: str) -> str:
    if "%" in hostname or _contains_unsafe_host_character(hostname):
        raise ValueError("invalid_hostname_character")

    try:
        return ipaddress.ip_address(hostname).compressed.lower()
    except ValueError:
        pass

    if ":" in hostname or _looks_like_legacy_ipv4(hostname):
        raise ValueError("invalid_ip_address")

    ascii_labels: list[str] = []
    normalized_labels: list[str] = []
    for label in hostname.split("."):
        if not label:
            raise ValueError("empty_hostname_label")
        normalized_label = unicodedata.normalize("NFC", label)
        if _contains_unsafe_host_character(normalized_label):
            raise ValueError("invalid_hostname_character")
        try:
            ascii_label = normalized_label.encode("idna").decode("ascii")
            decoded_label = ascii_label.encode("ascii").decode("idna")
            canonical_a_label = decoded_label.encode("idna").decode("ascii").lower()
            if canonical_a_label != ascii_label.lower():
                raise ValueError("invalid_idna_round_trip")
        except UnicodeError as exc:
            raise ValueError("invalid_idna_label") from exc
        if normalized_label.isascii() and normalized_label.lower().startswith("xn--"):
            if normalized_label != canonical_a_label:
                raise ValueError("noncanonical_idna_label")
            if _contains_unsafe_host_character(decoded_label):
                raise ValueError("invalid_idna_label")
        elif not normalized_label.isascii():
            canonical_unicode = unicodedata.normalize("NFC", decoded_label)
            if canonical_unicode.lower() != normalized_label.lower():
                raise ValueError("noncanonical_unicode_label")
        if not _DOMAIN_LABEL.fullmatch(ascii_label):
            raise ValueError("invalid_hostname_label")
        ascii_labels.append(ascii_label)
        normalized_labels.append(normalized_label)

    if len(".".join(ascii_labels).encode("ascii")) > 253:
        raise ValueError("hostname_too_long")
    return ".".join(ascii_labels).lower()


def _raw_hostname(netloc: str) -> str:
    authority = netloc.rsplit("@", 1)[-1]
    if authority.startswith("["):
        closing_bracket = authority.find("]")
        if closing_bracket < 0:
            raise ValueError("invalid_ipv6_brackets")
        return authority[1:closing_bracket]
    if ":" in authority:
        return authority.rsplit(":", 1)[0]
    return authority


def _normalize_miniapp_url(value: str, *, root_only: bool = True) -> str:
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        parsed.port
        raw_hostname = _raw_hostname(parsed.netloc)
        normalized_hostname = (
            _validate_miniapp_hostname(raw_hostname) if hostname else raw_hostname
        )
    except ValueError as exc:
        raise RuntimeError("invalid_settings:miniapp_url") from exc

    scheme = parsed.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or any(character.isspace() for character in candidate)
        or (scheme == "http" and hostname.lower() not in _LOCAL_MINIAPP_HOSTS)
        or (
            root_only
            and (parsed.path not in {"", "/"} or parsed.query or parsed.fragment)
        )
    ):
        raise RuntimeError("invalid_settings:miniapp_url")

    path = "" if parsed.path == "/" else parsed.path
    host_authority = (
        f"[{normalized_hostname}]" if ":" in normalized_hostname else normalized_hostname
    )
    port = parsed.port
    if port is None or (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        netloc = host_authority
    else:
        netloc = f"{host_authority}:{port}"
    return urlunsplit((scheme, netloc, path, parsed.query, parsed.fragment))


def _normalize_external_url(value: str, setting_name: str) -> str:
    try:
        return _normalize_miniapp_url(value, root_only=False)
    except RuntimeError as exc:
        raise RuntimeError(f"invalid_settings:{setting_name}") from exc


def _normalize_miniapp_origin(value: str, miniapp_url: str) -> str:
    try:
        normalized = _normalize_miniapp_url(value)
        parsed = urlsplit(normalized)
        miniapp = urlsplit(miniapp_url)
        if parsed.path or parsed.query or parsed.fragment:
            raise ValueError("origin_has_non_origin_components")
        if (
            parsed.scheme.lower(),
            (parsed.hostname or "").lower(),
            parsed.port,
        ) != (
            miniapp.scheme.lower(),
            (miniapp.hostname or "").lower(),
            miniapp.port,
        ):
            raise ValueError("origin_mismatch")
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    except (RuntimeError, ValueError) as exc:
        raise RuntimeError("invalid_settings:miniapp_origin") from exc


def _validate_admin_credentials(username: str, password: str) -> None:
    if (
        not 1 <= len(username) <= 128
        or username != username.strip()
        or ":" in username
        or not all(" " <= character <= "~" for character in username)
    ):
        raise RuntimeError("invalid_settings:ADMIN_USERNAME")
    if (
        not 12 <= len(password) <= 256
        or not all(" " <= character <= "~" for character in password)
        or password.casefold() == username.casefold()
        or password.casefold() in {"password", "admin-password", "change-me", "changeme"}
    ):
        raise RuntimeError("invalid_settings:ADMIN_PASSWORD")


def _retention_days(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"invalid_settings:{name}") from exc
    if not minimum <= value <= maximum or str(value) != raw:
        raise RuntimeError(f"invalid_settings:{name}")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str
    bot_token: str
    miniapp_url: str
    miniapp_origin: str
    admin_username: str
    admin_password: str
    analytics_webhook_url: str | None
    application_secret: str = "test-only-application-secret-1234567890"
    timezone: str = "Europe/Moscow"
    diagnostic_retention_days: int = 365
    in_progress_retention_days: int = 30

    @classmethod
    def from_env(cls, *, require_admin: bool = True) -> "Settings":
        required = {
            "database_url": os.getenv("DATABASE_URL", "").strip(),
            "bot_token": os.getenv("BOT_TOKEN", "").strip(),
            "miniapp_url": os.getenv("MINIAPP_URL", "").strip(),
            "miniapp_origin": os.getenv("MINIAPP_ORIGIN", "").strip(),
            "application_secret": os.getenv("APPLICATION_SECRET", "").strip(),
        }
        admin_username = os.getenv("ADMIN_USERNAME", "") if require_admin else ""
        admin_password = os.getenv("ADMIN_PASSWORD", "") if require_admin else ""
        missing = [key for key, value in required.items() if not value]
        if require_admin and not admin_username:
            missing.append("admin_username")
        if require_admin and not admin_password:
            missing.append("admin_password")
        if missing:
            raise RuntimeError("missing_settings:" + ",".join(sorted(missing)))
        if require_admin:
            _validate_admin_credentials(admin_username, admin_password)
        if not _BOT_TOKEN.fullmatch(required["bot_token"]):
            raise RuntimeError("invalid_settings:BOT_TOKEN")
        if (
            not _APPLICATION_SECRET.fullmatch(required["application_secret"])
            or required["application_secret"] in _APPLICATION_SECRET_PLACEHOLDERS
            or required["application_secret"] == required["bot_token"]
            or (
                require_admin
                and required["application_secret"] == admin_password
            )
        ):
            raise RuntimeError("invalid_settings:APPLICATION_SECRET")
        required["miniapp_url"] = _normalize_miniapp_url(required["miniapp_url"])
        required["miniapp_origin"] = _normalize_miniapp_origin(
            required["miniapp_origin"], required["miniapp_url"]
        )
        analytics_url = (os.getenv("ANALYTICS_WEBHOOK_URL") or "").strip()
        if analytics_url:
            analytics_url = _normalize_external_url(
                analytics_url, "analytics_webhook_url"
            )
        timezone = os.getenv("TIMEZONE", "Europe/Moscow").strip()
        try:
            if not 1 <= len(timezone) <= 64 or any(character.isspace() for character in timezone):
                raise ValueError("invalid_timezone")
            ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise RuntimeError("invalid_settings:TIMEZONE") from exc
        return cls(
            **required,
            admin_username=admin_username,
            admin_password=admin_password,
            analytics_webhook_url=analytics_url or None,
            timezone=timezone,
            diagnostic_retention_days=_retention_days(
                "DIAGNOSTIC_RETENTION_DAYS", 365, 31, 3650
            ),
            in_progress_retention_days=_retention_days(
                "IN_PROGRESS_RETENTION_DAYS", 30, 1, 365
            ),
        )
