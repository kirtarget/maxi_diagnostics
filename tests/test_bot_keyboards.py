from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from diagnostic.school import LinksConfig, SchoolConfig, load_school


SAMPLE_SCHOOL = Path(__file__).resolve().parents[1] / "tests/fixtures/sample-school"


def _buttons(keyboard):
    return [button for row in keyboard.inline_keyboard for button in row]


def test_offer_button_comes_from_school_links():
    from diagnostic.bot.keyboards import result_keyboard

    school = load_school(SAMPLE_SCHOOL)
    keyboard = result_keyboard(school, 101, "attempt-1", "full")
    buttons = _buttons(keyboard)
    configured_offer = school.links.offers[0]

    offer = next(
        button
        for button in buttons
        if (button.url or "").startswith(str(configured_offer.url))
    )
    query = parse_qs(urlparse(offer.url).query)
    assert query == {
        "utm_source": ["telegram"],
        "utm_medium": ["bot"],
        "utm_campaign": ["diagnostic"],
        "utm_content": [configured_offer.id],
    }


def test_webapp_and_home_keyboards_use_configured_miniapp_url():
    from diagnostic.bot.keyboards import home_keyboard, webapp_keyboard

    miniapp_url = "https://diagnostic.school.example/app"
    school = load_school(SAMPLE_SCHOOL)

    assert _buttons(webapp_keyboard(school, miniapp_url))[0].web_app.url == miniapp_url
    assert any(
        button.web_app and button.web_app.url == miniapp_url
        for button in _buttons(home_keyboard(school, miniapp_url, 101))
    )


def test_empty_optional_offers_leave_navigation_usable():
    from diagnostic.bot.keyboards import home_keyboard, result_keyboard

    school = load_school(SAMPLE_SCHOOL)
    school_without_offers = SchoolConfig(
        root=school.root,
        brand=school.brand,
        links=LinksConfig(
            website=school.links.website,
            support=school.links.support,
            privacy=school.links.privacy,
            offers=[],
        ),
    )

    assert _buttons(result_keyboard(school_without_offers, 101, "attempt-1", "quick"))
    assert _buttons(
        home_keyboard(school_without_offers, "https://diagnostic.school.example", 101)
    )


def test_non_english_school_labels_flow_through_commands_and_all_keyboards():
    from diagnostic.bot.keyboards import (
        home_keyboard,
        result_keyboard,
        results_keyboard,
        webapp_keyboard,
    )
    from diagnostic.bot.main import build_bot_commands

    school = load_school(SAMPLE_SCHOOL)
    miniapp_url = "https://diagnostic.school.example/app"
    interface = school.brand.interface
    offer_button = school.links.offers[0].button

    assert [command.description for command in build_bot_commands(school)] == [
        interface.command_start,
        interface.command_diagnostics,
        interface.command_results,
        interface.command_plan,
    ]
    assert [button.text for button in _buttons(webapp_keyboard(school, miniapp_url))] == [
        interface.start_diagnostic
    ]
    assert [button.text for button in _buttons(home_keyboard(school, miniapp_url, 101))] == [
        interface.open_diagnostic,
        interface.results,
        interface.plan,
        offer_button,
    ]
    assert [
        button.text
        for button in _buttons(
            result_keyboard(
                school,
                101,
                "attempt-1",
                "quick",
                miniapp_url=miniapp_url,
            )
        )
    ] == [
        offer_button,
        interface.plan,
        interface.results,
        interface.take_full_diagnostic,
        interface.home,
    ]
    assert [
        button.text
        for button in _buttons(
            result_keyboard(
                school,
                101,
                "attempt-1",
                "full",
                miniapp_url=miniapp_url,
            )
        )
    ] == [
        offer_button,
        interface.plan,
        interface.results,
        interface.check_another_subject,
        interface.home,
    ]
    assert [
        button.text
        for button in _buttons(
            results_keyboard(
                school,
                [
                    {
                        "attempt_id": "attempt-1",
                        "subject": "Математика",
                        "mode": "quick",
                        "completed_at": None,
                    }
                ],
                miniapp_url,
            )
        )
    ] == [
        f"Математика · {interface.quick_result} · {interface.ready_result}",
        interface.take_another_diagnostic,
        interface.home,
    ]


def test_result_date_is_rendered_in_configured_school_timezone():
    from diagnostic.bot.keyboards import results_keyboard

    school = load_school(SAMPLE_SCHOOL)
    keyboard = results_keyboard(
        school,
        [{
            "attempt_id": "attempt-1", "subject": "Математика", "mode": "quick",
            "completed_at": datetime(2026, 8, 10, 21, 30, tzinfo=timezone.utc),
        }],
        "https://diagnostic.school.example",
        timezone_name="Europe/Moscow",
    )

    assert "11.08" in _buttons(keyboard)[0].text
