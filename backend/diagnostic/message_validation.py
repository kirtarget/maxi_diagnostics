"""Dependency-free validation for school-owned Telegram HTML templates."""

from __future__ import annotations

from collections.abc import Mapping
from html.parser import HTMLParser
from string import Formatter
from urllib.parse import urlsplit
import re
import unicodedata


ALLOWED_PLACEHOLDERS = frozenset({
    "school_name", "school_short_name", "primary_offer_label", "primary_offer_url",
    "website_url", "support_url", "privacy_url", "subject", "mode",
})
_KEY_PLACEHOLDERS = {
    "NOT_STARTED": ALLOWED_PLACEHOLDERS - {"subject", "mode"},
    "LIVES_REFILL": ALLOWED_PLACEHOLDERS - {"subject", "mode"},
    "STREAK_SAVE": ALLOWED_PLACEHOLDERS - {"subject", "mode"},
}
_ALLOWED_HTML_TAGS = frozenset({
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code",
    "pre", "blockquote", "a",
})
_SAFE_ENTITIES = frozenset({"amp", "lt", "gt", "quot"})
_MARKUP_TOKEN = re.compile(
    r"</?[A-Za-z][^<>]*>|&(?:amp|lt|gt|quot|#[0-9]{1,7}|#x[0-9A-Fa-f]{1,6});"
)

# The product speaks to students in one voice: informal "ты", never the formal
# "вы". These are the tell-tale markers of formal Russian address — the
# pronoun family plus a short list of common formal imperative verbs.
_FORMAL_ADDRESS_VERBS = (
    "откройте", "выберите", "пройдите", "нажмите", "продолжите",
    "посмотрите", "проверьте", "попробуйте",
)
FORMAL_ADDRESS_PATTERN = re.compile(
    r"\b(?:вы|вас|вам|вами|ваш\w*|" + "|".join(_FORMAL_ADDRESS_VERBS) + r")\b",
    re.IGNORECASE,
)


def find_formal_address(text: str) -> list[str]:
    """Return every formal-address marker found in ``text`` (empty if none)."""
    return FORMAL_ADDRESS_PATTERN.findall(text)


class _TelegramHtmlValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _ALLOWED_HTML_TAGS:
            raise ValueError("message_html_invalid")
        if tag in {"pre", "code"} and self.stack or any(
            parent in {"pre", "code"} for parent in self.stack
        ):
            raise ValueError("message_html_invalid")
        if tag == "a":
            if "a" in self.stack or len(attrs) != 1 or attrs[0][0] != "href" or attrs[0][1] is None:
                raise ValueError("message_html_invalid")
            href = attrs[0][1]
            if href not in {
                "{primary_offer_url}", "{website_url}", "{support_url}", "{privacy_url}",
            }:
                parsed = urlsplit(href)
                if (
                    parsed.scheme != "https" or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                ):
                    raise ValueError("message_html_invalid")
        elif attrs:
            raise ValueError("message_html_invalid")
        self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag, attrs
        raise ValueError("message_html_invalid")

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack.pop() != tag:
            raise ValueError("message_html_invalid")

    def handle_entityref(self, name: str) -> None:
        if name not in _SAFE_ENTITIES:
            raise ValueError("message_html_invalid")

    def handle_charref(self, name: str) -> None:
        try:
            codepoint = int(name[1:], 16) if name.casefold().startswith("x") else int(name)
        except ValueError as exc:
            raise ValueError("message_html_invalid") from exc
        if not 0 < codepoint <= 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
            raise ValueError("message_html_invalid")
        category = unicodedata.category(chr(codepoint))
        if category.startswith("C") or category in {"Zl", "Zp"}:
            raise ValueError("message_html_invalid")

    def handle_comment(self, data: str) -> None:
        del data
        raise ValueError("message_html_invalid")

    def handle_decl(self, decl: str) -> None:
        del decl
        raise ValueError("message_html_invalid")

    def handle_pi(self, data: str) -> None:
        del data
        raise ValueError("message_html_invalid")

    def close(self) -> None:
        super().close()
        if self.stack:
            raise ValueError("message_html_invalid")


def validate_message_template(
    key: str, template: str, values: Mapping[str, str]
) -> str:
    if any(
        unicodedata.category(character).startswith("C")
        or unicodedata.category(character) in {"Zl", "Zp"}
        for character in template
    ):
        raise ValueError("message_text_invalid")
    try:
        parsed_fields = tuple(Formatter().parse(template))
    except ValueError as exc:
        raise ValueError("message_placeholder_invalid") from exc
    allowed_placeholders = _KEY_PLACEHOLDERS.get(key, ALLOWED_PLACEHOLDERS)
    for _literal, field_name, format_spec, conversion in parsed_fields:
        if field_name is None:
            continue
        if field_name not in allowed_placeholders or format_spec or conversion is not None:
            raise ValueError("message_placeholder_invalid")
    remaining = _MARKUP_TOKEN.sub("", template)
    if "<" in remaining or ">" in remaining or "&" in remaining:
        raise ValueError("message_html_invalid")
    parser = _TelegramHtmlValidator()
    parser.feed(template)
    parser.close()
    try:
        rendered = template.format_map(values)
    except (KeyError, ValueError, IndexError, AttributeError) as exc:
        raise ValueError("message_placeholder_invalid") from exc
    limit = 1024 if key in {"QUICK_COMPLETE", "FULL_COMPLETE"} else 4096
    if not rendered.strip() or len(rendered) > limit:
        raise ValueError("message_rendered_too_long")
    return template
