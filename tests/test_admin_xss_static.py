from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_ROOT = ROOT / "backend" / "diagnostic" / "admin"


def test_admin_script_uses_safe_dom_apis_and_browser_managed_basic_auth():
    source = (ADMIN_ROOT / "static" / "admin.js").read_text(encoding="utf-8")
    lowered = source.lower()

    for forbidden in (".innerhtml", "insertadjacenthtml", "document.write", "eval(", "onclick=", "localstorage", "sessionstorage", "authorization", "btoa("):
        assert forbidden not in lowered
    assert "textContent" in source
    assert "createElement" in source
    assert "addEventListener" in source
    assert 'credentials: "same-origin"' in source
    assert '"Content-Type": "application/json"' in source


def test_admin_templates_are_local_autoescaped_and_have_no_inline_handlers():
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ADMIN_ROOT / "templates").glob("*.html"))
    lowered = source.lower()

    assert "|safe" not in lowered
    assert not re.search(r"<script[^>]+src=[\"']https?://", lowered)
    assert not re.search(r"\son[a-z]+\s*=", lowered)
    assert "admin_password" not in lowered
    assert "admin_username" not in lowered


def test_admin_static_files_contain_no_secret_or_legacy_product_surface():
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ADMIN_ROOT / "static").glob("*.*"))
    lowered = source.lower()

    for forbidden in ("bot_token", "admin_password", "initdata", "amocrm", "curator", "slivy", "vkontakte", "telegram_username", "first_name", "answers"):
        assert forbidden not in lowered
