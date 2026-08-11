"""Safe rendering for administrator-editable Telegram HTML messages."""

from __future__ import annotations

import html
from collections.abc import Mapping

from diagnostic.db import messages as message_store
from diagnostic.message_validation import validate_message_template as _validate_template
from diagnostic.school import SchoolConfig


def validate_message_template(key: str, template: str, school: SchoolConfig) -> str:
    values = _safe_values(school, {"subject": "&" * 128, "mode": "full"})
    return _validate_template(key, template, values)


def _row_text(row: object) -> str | None:
    if row is None:
        return None
    if isinstance(row, Mapping):
        value = row.get("text")
    else:
        try:
            value = row["text"]  # type: ignore[index]
        except (KeyError, TypeError):
            value = getattr(row, "text", None)
    return value if isinstance(value, str) and value.strip() else None


def _safe_values(school: SchoolConfig, context: Mapping[str, object]) -> dict[str, str]:
    primary_offer = school.links.offers[0] if school.links.offers else None
    values = {name: str(value) for name, value in context.items()}
    values.update(
        {
            "school_name": school.brand.name,
            "school_short_name": school.brand.short_name,
            "primary_offer_label": (
                primary_offer.label if primary_offer else school.brand.name
            ),
            "primary_offer_url": str(
                primary_offer.url if primary_offer else school.links.website
            ),
            "website_url": str(school.links.website),
            "support_url": str(school.links.support),
            "privacy_url": str(school.links.privacy),
        }
    )
    return {name: html.escape(value, quote=True) for name, value in values.items()}


def _format_or_none(template: str, values: Mapping[str, str]) -> str | None:
    try:
        return template.format_map(values)
    except (KeyError, ValueError, IndexError, AttributeError):
        return None


async def render_message(key: str, school: SchoolConfig, **context: object) -> str:
    """Render trusted template HTML with every inserted value HTML-escaped."""
    row = await message_store.get_message(key)
    stored_template = _row_text(row)
    default_template = school.brand.messages.keyed().get(
        key, school.brand.messages.generic
    )
    values = _safe_values(school, context)

    if stored_template:
        try:
            validate_message_template(key, stored_template, school)
        except ValueError:
            stored_template = None
        if stored_template:
            rendered = _format_or_none(stored_template, values)
            if rendered is not None and len(rendered) <= 4096:
                return rendered

    rendered = _format_or_none(default_template, values)
    if rendered is not None and len(rendered) <= 4096:
        return rendered
    return school.brand.messages.generic.format_map(values)
