"""Shared normalization for short free-text diagnostic answers."""

from __future__ import annotations

import re
import unicodedata


DEFAULT_TEXT_ANSWER_LENGTH = 80
MAX_TEXT_ANSWER_LENGTH = 200

_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCTUATION = ".,;!?"
_CHARACTER_MAP = str.maketrans({"ё": "е", "–": "-", "—": "-"})


def normalize_text_answer(value: str) -> str:
    """Fold a free-text answer to the form both sides of a comparison share.

    NFC, trimmed, lowercase, ``ё`` folded to ``е``, runs of whitespace
    collapsed to one space, trailing sentence punctuation dropped, and every
    dash variant unified.  Pure: no length or character-class judgement here.
    """
    text = unicodedata.normalize("NFC", value).strip().lower()
    text = _WHITESPACE.sub(" ", text)
    text = text.rstrip(_TRAILING_PUNCTUATION).strip()
    return text.translate(_CHARACTER_MAP)


def is_valid_text_answer(
    value: object, max_length: int = DEFAULT_TEXT_ANSWER_LENGTH
) -> bool:
    """Whether ``value`` is a storable free-text answer of at most ``max_length``."""
    if not isinstance(value, str) or not 1 <= len(value) <= max_length:
        return False
    if any(unicodedata.category(character).startswith("C") for character in value):
        return False
    return bool(normalize_text_answer(value))
