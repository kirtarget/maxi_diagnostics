"""Initialize public school configuration without accepting secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from diagnostic.school import BrandConfig, LinksConfig  # noqa: E402
from diagnostic.settings import _normalize_miniapp_url  # noqa: E402


_BOT_USERNAME = re.compile(r"(?=.{5,32}\Z)[A-Za-z][A-Za-z0-9_]*[Bb][Oo][Tt]\Z")
_TEMPLATE_BRAND_HASH = "58b6e5151011bb5805ea04f8a5fde6f924d690e68aa989375ca8cb22c20355d8"
_TEMPLATE_LINKS_HASH = "77e52ab4d3694466275cfc9ff2e7ca4ee09de34429c71a94d04a9f6acad438c7"
_MARKER_NAME = ".initialized.json"
_MAX_CONFIG_BYTES = 1024 * 1024
_TEMPLATE_INSTALLATION_ID = "00000000-0000-4000-8000-000000000000"
_replace = os.replace


class ToolError(RuntimeError):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ToolError("invalid_arguments")


def _parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(description="Initialize public school configuration")
    parser.add_argument("--name", required=True)
    parser.add_argument("--short-name", required=True)
    parser.add_argument("--school-id", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--bot-username", required=True)
    parser.add_argument("--primary-color", required=True)
    parser.add_argument("--accent-color", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--root", help=argparse.SUPPRESS)
    return parser


def _safe_root(root: Path) -> Path:
    if root.is_symlink():
        raise ToolError("root_symlink_not_allowed")
    if not root.exists():
        raise ToolError("root_not_found")
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise ToolError("root_not_found") from exc
    if not resolved.is_dir():
        raise ToolError("root_not_directory")
    return resolved


def _validate_domain(value: str) -> tuple[str, str]:
    if not value or value != value.strip() or any(character in value for character in ":/@?#[]"):
        raise ToolError("invalid_domain")
    try:
        origin = _normalize_miniapp_url(f"https://{value}")
    except RuntimeError as exc:
        raise ToolError("invalid_domain") from exc
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ToolError("invalid_domain")
    return parsed.netloc, origin


def _ensure_safe_target(root: Path, path: Path) -> None:
    if path.is_symlink():
        raise ToolError("unsafe_config_path")
    if path.exists() and not path.is_file():
        raise ToolError("unsafe_config_path")
    try:
        relative_parts = path.parent.relative_to(root).parts
    except ValueError as exc:
        raise ToolError("unsafe_config_path") from exc
    current = root
    for part in relative_parts:
        current = current / part
        if current.is_symlink():
            raise ToolError("unsafe_config_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.parent.resolve().is_relative_to(root):
        raise ToolError("unsafe_config_path")


def _read_existing(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ToolError("unsafe_config_path")
    if not path.exists():
        return None
    if not path.is_file():
        raise ToolError("unsafe_config_path")
    try:
        size = path.stat().st_size
        if size > _MAX_CONFIG_BYTES:
            raise ToolError("config_too_large")
        with path.open("rb") as stream:
            payload = stream.read(_MAX_CONFIG_BYTES + 1)
    except OSError as exc:
        raise ToolError("config_unreadable") from exc
    if len(payload) > _MAX_CONFIG_BYTES:
        raise ToolError("config_too_large")
    return payload


def _decode_json(payload: bytes | None) -> dict:
    if payload is None:
        raise ToolError("school_not_pristine_use_force")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ToolError("school_not_pristine_use_force") from exc
    if not isinstance(value, dict):
        raise ToolError("school_not_pristine_use_force")
    return value


def _canonical_hash(value: dict) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_pristine_template(brand: dict, links: dict) -> bool:
    return (
        _canonical_hash(brand) == _TEMPLATE_BRAND_HASH
        and _canonical_hash(links) == _TEMPLATE_LINKS_HASH
    )


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _installation_id(existing_env: bytes | None) -> str:
    if existing_env is not None:
        try:
            text = existing_env.decode("utf-8")
        except UnicodeError as exc:
            raise ToolError("config_unreadable") from exc
        match = re.search(
            r"(?m)^INSTALLATION_ID=([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$",
            text,
        )
        if match and match.group(1) != _TEMPLATE_INSTALLATION_ID:
            return match.group(1)
    return str(uuid.uuid4())


def _stage(path: Path, payload: bytes) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _restore(path: Path, original: bytes | None) -> None:
    if path.is_symlink():
        raise OSError("rollback_target_unsafe")
    if original is None:
        if path.exists():
            path.unlink()
        return
    temporary = _stage(path, original)
    try:
        _replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _commit_outputs(root: Path, outputs: tuple[tuple[Path, bytes], ...]) -> None:
    originals: dict[Path, bytes | None] = {}
    staged: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for path, payload in outputs:
            _ensure_safe_target(root, path)
            originals[path] = _read_existing(path)
            staged[path] = _stage(path, payload)
        for path, _ in outputs:
            _ensure_safe_target(root, path)
            if _read_existing(path) != originals[path]:
                raise ToolError("config_changed_during_initialization")
            temporary = staged[path]
            _replace(temporary, path)
            staged.pop(path)
            replaced.append(path)
    except (OSError, ToolError) as exc:
        rollback_failed = False
        for path in reversed(replaced):
            try:
                _restore(path, originals[path])
            except OSError:
                rollback_failed = True
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        if rollback_failed:
            raise ToolError("initialization_rollback_failed") from exc
        if isinstance(exc, ToolError) and str(exc) == "config_changed_during_initialization":
            raise
        raise ToolError("initialization_write_failed") from exc
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def initialize_school(
    *, root: Path, name: str, short_name: str, school_id: str, domain: str,
    bot_username: str, primary_color: str, accent_color: str, force: bool = False,
) -> tuple[str, str]:
    root = _safe_root(root)
    school_root = root / "school"
    if school_root.is_symlink():
        raise ToolError("unsafe_school_path")
    if not school_root.exists() or not school_root.is_dir():
        raise ToolError("school_not_pristine_use_force")
    domain, origin = _validate_domain(domain)
    if not _BOT_USERNAME.fullmatch(bot_username):
        raise ToolError("invalid_bot_username")

    env_path = root / ".env.example"
    brand_path = school_root / "brand.json"
    links_path = school_root / "links.json"
    marker_path = school_root / _MARKER_NAME
    for path in (env_path, brand_path, links_path, marker_path):
        _ensure_safe_target(root, path)
    marker_payload = _read_existing(marker_path)
    if marker_payload is not None and not force:
        raise ToolError("school_already_initialized_use_force")
    existing_brand = _decode_json(_read_existing(brand_path))
    existing_links = _decode_json(_read_existing(links_path))
    installation_id = _installation_id(_read_existing(env_path))
    if marker_payload is None and not force and not _is_pristine_template(existing_brand, existing_links):
        raise ToolError("school_not_pristine_use_force")

    brand_data = dict(existing_brand)
    brand_data.update(
        {
            "school_id": school_id,
            "name": name,
            "short_name": short_name,
            "colors": {
                **dict(existing_brand.get("colors") or {}),
                "primary": primary_color,
                "accent": accent_color,
            },
        }
    )
    try:
        brand = BrandConfig.model_validate(brand_data)
    except Exception as exc:
        fields = ("school_id", "short_name", "name", "primary_color", "accent_color")
        error_text = str(exc).lower()
        for field in fields:
            if field.replace("_color", "") in error_text:
                raise ToolError(f"invalid_{field}") from exc
        raise ToolError("invalid_brand_config") from exc

    links_data = {
        "website": origin,
        "support": f"{origin}/support",
        "privacy": f"{origin}/privacy",
        "offers": [
            {
                "id": "preparation", "label": "Preparation program",
                "button": "Learn more", "url": f"{origin}/program",
                "recovery_share": 10,
            }
        ],
    }
    try:
        links = LinksConfig.model_validate(links_data)
    except Exception as exc:
        raise ToolError("invalid_links_config") from exc

    env_payload = (
        "POSTGRES_DB=diagnostic\n"
        f"IMAGE_NAMESPACE={school_id}-diagnostic\n"
        f"INSTALLATION_ID={installation_id}\n"
        "POSTGRES_USER=diagnostic\n"
        "POSTGRES_PASSWORD=\n"
        "DATABASE_URL=\n"
        "BOT_TOKEN=\n"
        "BOT_POLLING_ENABLED=true\n"
        "APPLICATION_SECRET=\n"
        f"BOT_USERNAME={bot_username}\n"
        f"MINIAPP_URL={origin}\n"
        f"MINIAPP_ORIGIN={origin}\n"
        "ADMIN_USERNAME=admin\n"
        "ADMIN_PASSWORD=\n"
        "ANALYTICS_WEBHOOK_URL=\n"
        "TIMEZONE=Europe/Moscow\n"
    ).encode("utf-8")
    brand_payload = _json_bytes(brand.model_dump(mode="json"))
    links_payload = _json_bytes(links.model_dump(mode="json"))
    marker_output = _json_bytes({"format": 1, "school_id": school_id})

    BrandConfig.model_validate(json.loads(brand_payload.decode("utf-8")))
    LinksConfig.model_validate(json.loads(links_payload.decode("utf-8")))
    if json.loads(marker_output.decode("utf-8")) != {"format": 1, "school_id": school_id}:
        raise ToolError("marker_validation_failed")
    _commit_outputs(
        root,
        (
            (env_path, env_payload),
            (brand_path, brand_payload),
            (links_path, links_payload),
            (marker_path, marker_output),
        ),
    )
    return school_id, domain


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    try:
        arguments, extras = _parser().parse_known_args(argv)
        if extras:
            raise ToolError("unsupported_argument")
        selected_root = root or (Path(arguments.root) if arguments.root else REPOSITORY_ROOT)
        school_id, domain = initialize_school(
            root=selected_root, name=arguments.name, short_name=arguments.short_name,
            school_id=arguments.school_id, domain=arguments.domain,
            bot_username=arguments.bot_username, primary_color=arguments.primary_color,
            accent_color=arguments.accent_color, force=arguments.force,
        )
    except ToolError as exc:
        print(f"ERROR {exc}")
        return 1
    except (OSError, UnicodeError, json.JSONDecodeError):
        print("ERROR initialization_failed")
        return 1
    print(f"OK initialized school={school_id} domain={domain}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
