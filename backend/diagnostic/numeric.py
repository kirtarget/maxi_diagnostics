"""Shared deploy-safe grammar for numeric diagnostic answers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re


MAX_NUMERIC_ANSWER_LENGTH = 64
NUMERIC_ANSWER_PATTERN = re.compile(
    r"[+-]?(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)(?:[eE][+-]?[0-9]{1,3})?\Z"
)


def normalize_numeric_answer(value: object) -> Decimal | None:
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_NUMERIC_ANSWER_LENGTH:
        return None
    if value != value.strip() or not NUMERIC_ANSWER_PATTERN.fullmatch(value):
        return None
    try:
        normalized = Decimal(value.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return normalized if normalized.is_finite() else None


def is_valid_numeric_answer(value: object) -> bool:
    return normalize_numeric_answer(value) is not None
