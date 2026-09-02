import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from diagnostic.school import load_school, validate_asset_bytes
from diagnostic.settings import Settings


INTERFACE_LABELS = {
    "command_start": "Open menu",
    "command_diagnostics": "Start diagnostic",
    "command_results": "My results",
    "command_plan": "My plan",
    "start_diagnostic": "Start diagnostic",
    "open_diagnostic": "Open diagnostic",
    "results": "My results",
    "plan": "My plan",
    "home": "Home",
    "take_full_diagnostic": "Take full diagnostic",
    "check_another_subject": "Check another subject",
    "take_another_diagnostic": "Take another diagnostic",
    "quick_result": "quick",
    "full_result": "full",
    "ready_result": "ready",
    "unassessed_full": "remaining full diagnostic",
    "results_heading": "Diagnostic results",
    "diagnostic_fallback": "Diagnostic",
    "plan_for": "Your plan for",
    "keep_strong": "Keep strong",
    "focus_next": "Focus next",
    "open_result_hint": "Open the result for the next step.",
    "result_not_found": "Result not found",
    "back": "Back",
    "task_label": "Task",
    "of_label": "of",
    "answer_label": "Your answer",
    "enter_answer": "Enter answer",
    "choose_option": "Choose option",
    "next_question": "Next question",
    "get_result": "Get result",
    "result_in_telegram": "Result in Telegram",
    "privacy_label": "Privacy",
    "support_label": "Support",
    "choose_label": "Choose",
    "close_diagnostic": "Close diagnostic",
    "illustration_alt": "Question illustration",
    "result_score": "Score",
    "result_correct": "Correct answers",
    "delivery_note": "The detailed report will appear in Telegram.",
}

MESSAGE_TEMPLATES = {
    "welcome": "Welcome to {school_name}.",
    "results_empty": "No completed diagnostics yet.",
    "plan_empty": "Your plan will appear here.",
    "data_erased": "Your data was erased. Try again in 15 minutes.",
    "quick_complete": "Your quick {subject} result is ready.",
    "full_complete": "Your full {subject} result is ready.",
    "not_started": "Start a diagnostic when you are ready.",
    "incomplete": "Continue your {subject} diagnostic.",
    "result_unviewed": "Your {subject} result is waiting.",
    "day_followup": "Review your {subject} result.",
    "quick_to_full": "Try the full diagnostic: {primary_offer_url}",
    "month_retest": "Retake your {subject} diagnostic in a month.",
    "generic": "{school_name}: open the diagnostic menu.",
}


def write_sample_school(root: Path) -> None:
    (root / "assets").mkdir(parents=True)
    (root / "brand.json").write_text(
        json.dumps(
            {
                "school_id": "demo-school",
                "name": "Demo school",
                "short_name": "Demo",
                "colors": {
                    "primary": "#5636D3",
                    "accent": "#C7F36B",
                    "background": "#F7F5EF",
                },
                "logo": "assets/logo.svg",
                "pdf": {
                    "header": "Diagnostic report",
                    "score_label": "Result",
                    "correct_label": "Correct answers",
                    "strong_topics_label": "Strong topics",
                    "growth_topics_label": "Growth topics",
                    "forecast_label": "Forecast",
                    "answer_label": "Your answer",
                },
                "interface": INTERFACE_LABELS,
                "messages": MESSAGE_TEMPLATES,
            }
        ),
        encoding="utf-8",
    )
    (root / "links.json").write_text(
        json.dumps(
            {
                "website": "https://school.example",
                "support": "https://t.me/demo_support",
                "privacy": "https://school.example/privacy",
                "offers": [
                    {
                        "id": "intensive",
                        "label": "Intensive",
                        "button": "Start preparation",
                        "url": "https://school.example/intensive",
                        "forecast_delta": 14,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "assets" / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40">'
        '<rect width="100" height="40" fill="#5636D3"/></svg>',
        encoding="utf-8",
    )


def test_load_school_returns_brand_and_offer_links(tmp_path: Path):
    write_sample_school(tmp_path)

    school = load_school(tmp_path)

    assert school.brand.school_id == "demo-school"
    assert school.links.offers[0].forecast_delta == 14
    assert school.resolve_asset("assets/logo.svg").is_file()


def test_brand_color_roles_have_backwards_compatible_defaults(tmp_path: Path):
    write_sample_school(tmp_path)

    school = load_school(tmp_path)

    assert school.brand.colors.signal == "#D8FF42"
    assert school.brand.colors.ink == "#101517"
    assert school.brand.colors.paper == "#F5F5F0"


def test_runtime_loader_rejects_symlinked_school_root(monkeypatch, tmp_path: Path):
    write_sample_school(tmp_path)
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path == tmp_path or original(path)
    )

    with pytest.raises(ValueError, match="school_root_invalid"):
        load_school(tmp_path)


def test_runtime_loader_rejects_symlinked_config_entry(monkeypatch, tmp_path: Path):
    write_sample_school(tmp_path)
    config_path = tmp_path / "brand.json"
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path == config_path or original(path)
    )

    with pytest.raises(ValueError, match="school_symlink_not_allowed"):
        load_school(tmp_path)


def test_raster_asset_rejects_decompression_bomb_dimensions(monkeypatch):
    class OversizedImage:
        def getSize(self):
            return 10_000, 10_000

    monkeypatch.setattr("diagnostic.school.ImageReader", lambda _: OversizedImage())

    with pytest.raises(ValueError, match="asset_invalid"):
        validate_asset_bytes("assets/oversized.png", b"not-empty")


def test_raster_asset_must_fully_decode(monkeypatch):
    class TruncatedImage:
        def getSize(self):
            return 1, 1

        def getRGBData(self):
            raise OSError("image file is truncated")

    monkeypatch.setattr("diagnostic.school.ImageReader", lambda _: TruncatedImage())

    with pytest.raises(ValueError, match="asset_invalid"):
        validate_asset_bytes("assets/truncated.png", b"valid-header-only")


def test_asset_inventory_bounds_repeated_raster_decode_work(tmp_path: Path, monkeypatch):
    from diagnostic.school import validate_asset_inventory

    class ExpensiveImage:
        def getSize(self):
            return 1000, 1000

        def getRGBData(self):
            return b"ok"

    asset = tmp_path / "assets" / "shared.png"
    asset.parent.mkdir()
    asset.write_bytes(b"small-compressed-image")
    monkeypatch.setattr("diagnostic.school.ImageReader", lambda _: ExpensiveImage())

    with pytest.raises(ValueError, match="asset_reference_workload_too_large"):
        validate_asset_inventory(tmp_path, ["assets/shared.png"] * 51)


@pytest.mark.parametrize(
    ("filename", "path", "value"),
    [
        ("brand.json", ("name",), "School\nName"),
        ("brand.json", ("pdf", "header"), "Bad\x00Header"),
        ("brand.json", ("interface", "home"), "Home\nNow"),
        ("links.json", ("offers", 0, "label"), "Bad\tOffer"),
    ],
)
def test_school_text_rejects_runtime_unsafe_control_characters(
    tmp_path: Path, filename: str, path: tuple, value: str,
):
    write_sample_school(tmp_path)
    target = tmp_path / filename
    payload = json.loads(target.read_text(encoding="utf-8"))
    current = payload
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError):
        load_school(tmp_path)


@pytest.mark.parametrize(
    ("filename", "path", "value"),
    [
        ("brand.json", ("name",), "School \u5b66"),
        ("brand.json", ("pdf", "header"), "Report \U0001f600"),
        ("links.json", ("offers", 0, "label"), "Course \u5b66"),
    ],
)
def test_school_rejects_pdf_text_missing_from_bundled_fonts(
    tmp_path: Path, filename: str, path: tuple, value: str,
):
    write_sample_school(tmp_path)
    target = tmp_path / filename
    payload = json.loads(target.read_text(encoding="utf-8"))
    current = payload
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="school_config_invalid"):
        load_school(tmp_path)


def test_load_school_rejects_path_traversal():
    school = load_school(Path("school"))

    with pytest.raises(ValueError, match="school_asset_outside_root"):
        school.resolve_asset("../.env")


@pytest.mark.parametrize(
    "unsafe_markup",
    [
        '<svg:svg xmlns:svg="http://www.w3.org/2000/svg" width="10" height="10"><svg:script/></svg:svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" onload="run()"/>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><style>@import url(https://example.test/a.css)</style></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><image href="https://example.test/a.png"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="url(https://example.test/a.svg#paint)"/></svg>',
        r'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="u\72l(https://example.test/a.svg#paint)"/></svg>',
        r'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><style>@im\70ort "https://example.test/a.css";</style></svg>',
        '<?xml-stylesheet href="https://example.test/a.css"?><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>',
    ],
)
def test_load_school_rejects_structurally_unsafe_svg(tmp_path: Path, unsafe_markup: str):
    write_sample_school(tmp_path)
    (tmp_path / "assets/logo.svg").write_text(unsafe_markup, encoding="utf-8")

    with pytest.raises(ValueError, match="asset_unsafe_svg"):
        load_school(tmp_path)


def test_load_school_allows_internal_svg_references(tmp_path: Path):
    write_sample_school(tmp_path)
    (tmp_path / "assets/logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        '<defs><circle id="dot" cx="5" cy="5" r="4"/></defs>'
        '<use href="#dot"/></svg>',
        encoding="utf-8",
    )

    assert load_school(tmp_path).brand.logo == "assets/logo.svg"


def test_asset_validator_rejects_a_single_node_path_command_bomb():
    path = " ".join("L1 1" for _ in range(20_000))
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        f'<path d="M0 0 {path}"/></svg>'
    ).encode("utf-8")

    with pytest.raises(ValueError, match="asset_too_complex"):
        validate_asset_bytes("assets/path.svg", svg)


def test_load_school_requires_exact_asset_path_casing(tmp_path: Path):
    write_sample_school(tmp_path)
    source = tmp_path / "assets/logo.svg"
    source.rename(tmp_path / "assets/Logo.svg")

    with pytest.raises(ValueError, match="asset_case_mismatch"):
        load_school(tmp_path)


@pytest.mark.parametrize(
    "asset",
    [
        "assets\\logo.svg",
        "assets/logo image.svg",
        "assets/логотип.svg",
        "assets/logo.webp",
        "assets/diagram..v2.svg",
        "../logo.svg",
    ],
)
def test_load_school_rejects_assets_that_are_not_portable_everywhere(
    tmp_path: Path, asset: str
):
    write_sample_school(tmp_path)
    brand_path = tmp_path / "brand.json"
    brand = json.loads(brand_path.read_text(encoding="utf-8"))
    brand["logo"] = asset
    brand_path.write_text(json.dumps(brand), encoding="utf-8")

    with pytest.raises(ValueError, match="school_config_invalid"):
        load_school(tmp_path)


@pytest.mark.parametrize(
    "asset",
    [
        "assets/CON.svg",
        "assets/nul.png",
        "assets/aux.jpg",
        "assets/com1/logo.svg",
        "assets/LPT9.figure.svg",
    ],
)
def test_asset_path_rejects_windows_reserved_device_names(asset: str):
    from diagnostic.school import validate_asset_path

    with pytest.raises(ValueError, match="invalid_asset_path"):
        validate_asset_path(asset)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda offer, links: offer.update(id=""),
        lambda offer, links: offer.update(label=" "),
        lambda offer, links: offer.update(button="x" * 65),
        lambda offer, links: offer.update(forecast_delta=101),
        lambda offer, links: links.update(offers=[offer] * 11),
        lambda offer, links: links.update(offers=[offer, dict(offer)]),
    ],
)
def test_load_school_rejects_unsafe_or_unbounded_offers(
    tmp_path: Path, mutation
):
    write_sample_school(tmp_path)
    links_path = tmp_path / "links.json"
    links = json.loads(links_path.read_text(encoding="utf-8"))
    offer = links["offers"][0]
    mutation(offer, links)
    links_path.write_text(json.dumps(links), encoding="utf-8")

    with pytest.raises(ValueError, match="school_config_invalid"):
        load_school(tmp_path)


@pytest.mark.parametrize(
    ("target", "url"),
    [
        ("website", "http://school.example"),
        ("support", "https://user:password@school.example/support"),
        ("privacy", "https://school.example/privacy#internal"),
        ("offer", "https://user:password@school.example/program"),
        ("offer", "https://school.example/program?" + "x" * 513),
    ],
)
def test_load_school_rejects_links_that_leak_credentials_or_downgrade_users(
    tmp_path: Path, target: str, url: str
):
    write_sample_school(tmp_path)
    links_path = tmp_path / "links.json"
    links = json.loads(links_path.read_text(encoding="utf-8"))
    if target == "offer":
        links["offers"][0]["url"] = url
    else:
        links[target] = url
    links_path.write_text(json.dumps(links), encoding="utf-8")

    with pytest.raises(ValueError, match="school_config_invalid"):
        load_school(tmp_path)


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_load_school_requires_a_strict_complete_interface_label_set(tmp_path: Path, mutation: str):
    write_sample_school(tmp_path)
    brand_path = tmp_path / "brand.json"
    brand = json.loads(brand_path.read_text(encoding="utf-8"))
    if mutation == "missing":
        del brand["interface"]["home"]
    else:
        brand["interface"]["unexpected_label"] = "Unexpected"
    brand_path.write_text(json.dumps(brand), encoding="utf-8")

    with pytest.raises(ValueError, match="school_config_invalid"):
        load_school(tmp_path)


@pytest.mark.parametrize("invalid_value", ["duplicate", "nonfinite"])
def test_load_school_rejects_ambiguous_nonstandard_json(
    tmp_path: Path, invalid_value: str
):
    write_sample_school(tmp_path)
    brand_path = tmp_path / "brand.json"
    payload = brand_path.read_text(encoding="utf-8")
    if invalid_value == "duplicate":
        payload = payload.replace(
            '"school_id": "demo-school"',
            '"school_id": "demo-school", "school_id": "other-school"',
            1,
        )
        error = "json_duplicate_key"
    else:
        payload = payload.replace('"name": "Demo school"', '"name": NaN', 1)
        error = "json_nonfinite_number"
    brand_path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        load_school(tmp_path)


def test_settings_normalizes_urls_and_optional_webhook(monkeypatch: pytest.MonkeyPatch):
    values = {
        "DATABASE_URL": "postgresql://user:password@localhost:5432/diagnostic_bot",
        "BOT_TOKEN": "123456:test-token",
        "MINIAPP_URL": "https://app.example/",
        "MINIAPP_ORIGIN": "https://app.example/",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "safe-password-123",
        "APPLICATION_SECRET": "stable-installation-secret-1234567890",
        "ANALYTICS_WEBHOOK_URL": "",
        "TIMEZONE": "Europe/Moscow",
        "BOT_POLLING_ENABLED": "false",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    settings = Settings.from_env()

    assert settings.miniapp_url == "https://app.example"
    assert settings.miniapp_origin == "https://app.example"
    assert settings.analytics_webhook_url is None
    assert settings.timezone == "Europe/Moscow"
    assert settings.diagnostic_retention_days == 365
    assert settings.in_progress_retention_days == 30
    assert settings.bot_polling_enabled is False
    assert settings.alert_chat_id is None
    assert settings.log_level == "INFO"


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("", None), ("4242", 4242), (" -100200300 ", -100200300)],
)
def test_alert_chat_id_is_optional_and_numeric(
    monkeypatch: pytest.MonkeyPatch, configured: str, expected,
):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("ALERT_CHAT_ID", configured)

    assert Settings.from_env().alert_chat_id == expected


@pytest.mark.parametrize("configured", ["0", "chat", "42.0", "+42", "1_000"])
def test_settings_rejects_an_unusable_alert_chat_id(
    monkeypatch: pytest.MonkeyPatch, configured: str,
):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("ALERT_CHAT_ID", configured)

    with pytest.raises(RuntimeError, match="invalid_settings:ALERT_CHAT_ID"):
        Settings.from_env()


@pytest.mark.parametrize(
    ("configured", "expected"), [("debug", "DEBUG"), ("WARNING", "WARNING")]
)
def test_log_level_is_normalized(
    monkeypatch: pytest.MonkeyPatch, configured: str, expected: str,
):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("LOG_LEVEL", configured)

    assert Settings.from_env().log_level == expected


@pytest.mark.parametrize("configured", ["verbose", "TRACE", "10"])
def test_settings_rejects_an_unknown_log_level(
    monkeypatch: pytest.MonkeyPatch, configured: str,
):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("LOG_LEVEL", configured)

    with pytest.raises(RuntimeError, match="invalid_settings:LOG_LEVEL"):
        Settings.from_env()


@pytest.mark.parametrize("configured", ["0", "yes", "FALSE ", "enabled"])
def test_settings_rejects_invalid_bot_polling_flag(
    monkeypatch: pytest.MonkeyPatch, configured: str,
):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("BOT_POLLING_ENABLED", configured)

    with pytest.raises(RuntimeError, match="invalid_settings:BOT_POLLING_ENABLED"):
        Settings.from_env()


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("DIAGNOSTIC_RETENTION_DAYS", "30"),
        ("DIAGNOSTIC_RETENTION_DAYS", "3651"),
        ("IN_PROGRESS_RETENTION_DAYS", "0"),
        ("IN_PROGRESS_RETENTION_DAYS", "366"),
        ("IN_PROGRESS_RETENTION_DAYS", "not-a-number"),
    ],
)
def test_settings_rejects_unsafe_retention_windows(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str,
):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv(variable, value)

    with pytest.raises(RuntimeError, match=f"invalid_settings:{variable}"):
        Settings.from_env()


def test_settings_reports_required_values_that_are_missing(monkeypatch: pytest.MonkeyPatch):
    for key in (
        "DATABASE_URL",
        "BOT_TOKEN",
        "MINIAPP_URL",
        "MINIAPP_ORIGIN",
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD",
        "APPLICATION_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(
        RuntimeError,
        match="missing_settings:admin_password,admin_username,application_secret,bot_token,database_url,miniapp_origin,miniapp_url",
    ):
        Settings.from_env()


def _set_required_settings(monkeypatch: pytest.MonkeyPatch, miniapp_url: str) -> None:
    try:
        parsed = urlsplit(miniapp_url.strip())
        origin = (
            f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme and parsed.netloc
            else "https://app.example"
        )
    except ValueError:
        origin = "https://app.example"
    values = {
        "DATABASE_URL": "postgresql://user:password@localhost:5432/diagnostic_bot",
        "BOT_TOKEN": "123456:test-token",
        "MINIAPP_URL": miniapp_url,
        "MINIAPP_ORIGIN": origin,
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "safe-password-123",
        "APPLICATION_SECRET": "stable-installation-secret-1234567890",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize(
    "configured",
    [
        "short", "contains spaces in this secret value", "a" * 129,
        "test-only-application-secret-1234567890",
    ],
)
def test_settings_rejects_unstable_application_secret(
    monkeypatch: pytest.MonkeyPatch, configured: str
):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("APPLICATION_SECRET", configured)

    with pytest.raises(RuntimeError, match="invalid_settings:APPLICATION_SECRET"):
        Settings.from_env()


def test_settings_keeps_application_secret_separate_from_bot_token(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_required_settings(monkeypatch, "https://app.example")

    settings = Settings.from_env()

    assert settings.application_secret == "stable-installation-secret-1234567890"
    assert settings.application_secret != settings.bot_token


def test_bot_runtime_settings_do_not_require_or_retain_admin_credentials(monkeypatch):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    settings = Settings.from_env(require_admin=False)

    assert settings.admin_username == ""
    assert settings.admin_password == ""


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("ADMIN_USERNAME", " admin"),
        ("ADMIN_USERNAME", "admin "),
        ("ADMIN_USERNAME", "admin:name"),
        ("ADMIN_USERNAME", "администратор"),
        ("ADMIN_USERNAME", "admin\tname"),
        ("ADMIN_USERNAME", "a" * 129),
        ("ADMIN_PASSWORD", "пароль"),
        ("ADMIN_PASSWORD", "password\n"),
        ("ADMIN_PASSWORD", "password\x7f"),
        ("ADMIN_PASSWORD", "short"),
        ("ADMIN_PASSWORD", "admin"),
        ("ADMIN_PASSWORD", "change-me"),
        ("ADMIN_PASSWORD", "p" * 257),
    ],
)
def test_settings_rejects_admin_credentials_incompatible_with_basic_auth(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv(variable, value)

    with pytest.raises(RuntimeError) as captured:
        Settings.from_env()

    assert str(captured.value) == f"invalid_settings:{variable}"


def test_settings_allows_printable_ascii_password_with_colon(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "safe:password")

    settings = Settings.from_env()

    assert settings.admin_password == "safe:password"


@pytest.mark.parametrize(
    ("configured", "normalized"),
    [
        (" https://app.example/ ", "https://app.example"),
        ("https://school.example", "https://school.example"),
        ("https://face.0xdead.example", "https://face.0xdead.example"),
        ("https://sub-domain.school.example:8443", "https://sub-domain.school.example:8443"),
        ("https://пример.рф", "https://xn--e1afmkfd.xn--p1ai"),
        ("https://май.example", "https://xn--80ash.example"),
        ("https://xn--e1afmkfd.xn--p1ai", "https://xn--e1afmkfd.xn--p1ai"),
        ("https://APP.Example:443", "https://app.example"),
        ("http://LOCALHOST:80", "http://localhost"),
        ("https://192.0.2.1:8443", "https://192.0.2.1:8443"),
        ("https://[2001:db8::1]:8443", "https://[2001:db8::1]:8443"),
        ("http://localhost:3000", "http://localhost:3000"),
        ("http://127.0.0.1:3000", "http://127.0.0.1:3000"),
        ("http://[::1]:3000", "http://[::1]:3000"),
    ],
)
def test_settings_accepts_https_and_narrow_local_http(
    monkeypatch: pytest.MonkeyPatch,
    configured: str,
    normalized: str,
):
    _set_required_settings(monkeypatch, configured)

    assert Settings.from_env().miniapp_url == normalized


@pytest.mark.parametrize(
    "configured",
    [
        "http://school.example/app",
        "javascript:alert(1)",
        "ftp://school.example/app",
        "school.example/app",
        "https://user:password@school.example/app",
        "https://school.example/app",
        "https://school.example?mode=quick",
        "https://school.example#result",
    ],
)
def test_settings_rejects_unsafe_miniapp_urls(
    monkeypatch: pytest.MonkeyPatch,
    configured: str,
):
    _set_required_settings(monkeypatch, configured)

    with pytest.raises(RuntimeError, match="invalid_settings:miniapp_url"):
        Settings.from_env()


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "http://app.example",
        "https://app.example/path",
        "https://app.example?query=1",
        "https://other.example",
    ],
)
def test_settings_rejects_unsafe_or_mismatched_miniapp_origin(
    monkeypatch: pytest.MonkeyPatch, origin: str
):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("MINIAPP_ORIGIN", origin)

    with pytest.raises(RuntimeError, match="invalid_settings:miniapp_origin"):
        Settings.from_env()


@pytest.mark.parametrize(
    "configured",
    [
        pytest.param("https://example..com/app", id="empty-middle-label"),
        pytest.param("https://.example.com/app", id="empty-leading-label"),
        pytest.param("https://example.com./app", id="empty-trailing-label"),
        pytest.param("https://./app", id="dot-host"),
        pytest.param("https://-example.com/app", id="leading-hyphen"),
        pytest.param("https://example-.com/app", id="trailing-hyphen"),
        pytest.param("https://exa%20mple.com/app", id="percent-encoded-space"),
        pytest.param("https://exa\nmple.com/app", id="control-character"),
        pytest.param("https://xn--.example/app", id="invalid-punycode"),
        pytest.param(f"https://{'a' * 64}.example/app", id="overlong-label"),
        pytest.param(
            "https://" + ".".join(["a" * 63] * 4) + "/app",
            id="overlong-host",
        ),
        pytest.param("https://999.999.999.999/app", id="numeric-ip-lookalike"),
        pytest.param("https://256.1.1.1/app", id="invalid-ipv4"),
        pytest.param("https://[2001:db8::1::1]/app", id="invalid-ipv6"),
        pytest.param("https://2001:db8::1/app", id="unbracketed-ipv6"),
        pytest.param("http://sub.localhost/app", id="localhost-subdomain-over-http"),
        pytest.param("http://127.0.0.2/app", id="other-loopback-over-http"),
    ],
)
def test_settings_rejects_malformed_miniapp_hosts(
    monkeypatch: pytest.MonkeyPatch,
    configured: str,
):
    _set_required_settings(monkeypatch, configured)

    with pytest.raises(RuntimeError, match="invalid_settings:miniapp_url"):
        Settings.from_env()


@pytest.mark.parametrize(
    "configured",
    [
        pytest.param("https://exam\u200dple.com/app", id="zero-width-joiner"),
        pytest.param("https://exam\u200cple.com/app", id="zero-width-non-joiner"),
        pytest.param("https://exam\u00adple.com/app", id="soft-hyphen"),
        pytest.param("https://exam\u2060ple.com/app", id="word-joiner"),
        pytest.param("https://exam\ue000ple.com/app", id="private-use"),
        pytest.param("https://exam\u0378ple.com/app", id="unassigned"),
        pytest.param("https://exam\u00a0ple.com/app", id="unicode-whitespace"),
        pytest.param("https://XN--E1AFMKFD.XN--P1AI/app", id="noncanonical-punycode"),
    ],
)
def test_settings_rejects_unsafe_or_noncanonical_unicode_hosts(
    monkeypatch: pytest.MonkeyPatch,
    configured: str,
):
    _set_required_settings(monkeypatch, configured)

    with pytest.raises(RuntimeError, match="invalid_settings:miniapp_url"):
        Settings.from_env()


@pytest.mark.parametrize(
    "configured",
    [
        pytest.param("https://0x7f000001/app", id="single-hex-integer"),
        pytest.param("https://2130706433/app", id="single-decimal-integer"),
        pytest.param("https://0177.0.0.1/app", id="octal-component"),
        pytest.param("https://127.1/app", id="shortened-ipv4"),
        pytest.param("https://127.0.0.0x1/app", id="mixed-decimal-hex"),
        pytest.param("https://0x7f.0.0.1/app", id="dotted-hex"),
        pytest.param("https://１２７.０.０.１/app", id="fullwidth-digits"),
        pytest.param("https://１２７．０．０．１/app", id="fullwidth-digits-and-dots"),
        pytest.param("https://١٢٧.٠.٠.١/app", id="arabic-indic-digits"),
    ],
)
def test_settings_rejects_legacy_or_unicode_numeric_ip_hosts(
    monkeypatch: pytest.MonkeyPatch,
    configured: str,
):
    _set_required_settings(monkeypatch, configured)

    with pytest.raises(RuntimeError, match="invalid_settings:miniapp_url"):
        Settings.from_env()


def test_url_validation_propagates_surrogate_rejection_directly():
    from diagnostic.settings import _normalize_miniapp_url

    with pytest.raises(RuntimeError, match="invalid_settings:miniapp_url"):
        _normalize_miniapp_url("https://exam\ud800ple.com/app")


@pytest.mark.parametrize("configured", ["http://analytics.example/events", "javascript:alert(1)", "https://user:pass@analytics.example/events"])
def test_settings_rejects_unsafe_analytics_webhook_url(monkeypatch, configured):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("ANALYTICS_WEBHOOK_URL", configured)

    with pytest.raises(RuntimeError, match="invalid_settings:analytics_webhook_url"):
        Settings.from_env()


def test_settings_normalizes_safe_analytics_webhook_url(monkeypatch):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("ANALYTICS_WEBHOOK_URL", " https://analytics.example/events ")

    assert Settings.from_env().analytics_webhook_url == "https://analytics.example/events"


@pytest.mark.parametrize(
    "configured",
    ["test-token", "1234:abcdefgh", "12345:short", "12345:bad token"],
)
def test_settings_rejects_invalid_bot_token_shape(monkeypatch, configured):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("BOT_TOKEN", configured)

    with pytest.raises(RuntimeError, match="invalid_settings:BOT_TOKEN"):
        Settings.from_env()


@pytest.mark.parametrize("configured", ["Mars/Base", "Europe/ Moscow", "x" * 65])
def test_settings_rejects_invalid_timezone(monkeypatch, configured):
    _set_required_settings(monkeypatch, "https://app.example")
    monkeypatch.setenv("TIMEZONE", configured)

    with pytest.raises(RuntimeError, match="invalid_settings:TIMEZONE"):
        Settings.from_env()
