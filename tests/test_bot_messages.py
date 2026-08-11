from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from diagnostic.school import load_school


SAMPLE_SCHOOL = Path(__file__).resolve().parents[1] / "tests/fixtures/sample-school"


@pytest.mark.asyncio
async def test_render_message_keeps_trusted_html_and_escapes_all_values(monkeypatch):
    from diagnostic import messages

    monkeypatch.setattr(
        messages.message_store,
        "get_message",
        AsyncMock(
            return_value={
                "text": (
                    "<b>{school_name}</b> {subject} "
                    '<a href="{primary_offer_url}">{primary_offer_label}</a>'
                )
            }
        ),
    )
    school = load_school(SAMPLE_SCHOOL)
    school.brand.name = '<img src=x onerror="alert(1)">'
    school.links.offers[0].label = "<script>alert(2)</script>"
    school.links.offers[0].url = "https://school.example/path?a=1&b=2"

    rendered = await messages.render_message(
        "WELCOME",
        school,
        subject='<a href="https://evil.example">math</a>',
    )

    assert rendered.startswith("<b>&lt;img")
    assert "<script>" not in rendered
    assert "&lt;a href=&quot;https://evil.example&quot;&gt;math&lt;/a&gt;" in rendered
    assert 'href="https://school.example/path?a=1&amp;b=2"' in rendered


@pytest.mark.asyncio
async def test_render_message_uses_generic_default_when_database_row_is_absent(monkeypatch):
    from diagnostic import messages

    monkeypatch.setattr(messages.message_store, "get_message", AsyncMock(return_value=None))

    school = load_school(SAMPLE_SCHOOL)
    rendered = await messages.render_message("WELCOME", school)

    assert school.brand.name in rendered


@pytest.mark.asyncio
async def test_invalid_admin_placeholder_falls_back_without_crashing(monkeypatch):
    from diagnostic import messages

    monkeypatch.setattr(
        messages.message_store,
        "get_message",
        AsyncMock(return_value={"text": "<b>{missing_admin_placeholder}</b>"}),
    )

    school = load_school(SAMPLE_SCHOOL)
    rendered = await messages.render_message("WELCOME", school)

    assert school.brand.name in rendered
    assert "missing_admin_placeholder" not in rendered


@pytest.mark.asyncio
async def test_caller_context_cannot_override_school_owned_placeholders(monkeypatch):
    from diagnostic import messages

    monkeypatch.setattr(
        messages.message_store,
        "get_message",
        AsyncMock(
            return_value={
                "text": (
                    "{school_name}|{school_short_name}|{primary_offer_label}|"
                    "{primary_offer_url}|{website_url}|{support_url}|{privacy_url}"
                )
            }
        ),
    )

    school = load_school(SAMPLE_SCHOOL)
    rendered = await messages.render_message(
        "WELCOME",
        school,
        school_name="Attacker school",
        school_short_name="Attacker",
        primary_offer_label="Attacker offer",
        primary_offer_url="javascript:alert(1)",
        website_url="https://evil.example",
        support_url="https://evil.example/support",
        privacy_url="https://evil.example/privacy",
    )

    offer = school.links.offers[0]
    assert rendered == "|".join(
        (
            school.brand.name,
            school.brand.short_name,
            offer.label,
            str(offer.url),
            str(school.links.website),
            str(school.links.support),
            str(school.links.privacy),
        )
    )
