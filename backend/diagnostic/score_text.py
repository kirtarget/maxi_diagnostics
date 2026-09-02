"""Shared Russian wording for the exam-score estimate.

The PDF, the bot and the Mini App all say the same thing about an estimate, so the
phrasing lives in one place. Reads persisted snapshots, so every input is a plain
mapping that may be missing or malformed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _plural(count: int, one: str, few: str, many: str) -> str:
    if count % 100 in range(11, 15):
        return many
    remainder = count % 10
    if remainder == 1:
        return one
    if remainder in (2, 3, 4):
        return few
    return many


def normalized_estimate(value: Any) -> dict[str, Any] | None:
    """Return the estimate only when it carries a usable kind, value and sample."""
    if not isinstance(value, Mapping):
        return None
    kind = value.get("kind")
    number = value.get("value")
    sample = value.get("sample_size")
    if kind not in {"test_score", "grade"}:
        return None
    if isinstance(number, bool) or not isinstance(number, int):
        return None
    if isinstance(sample, bool) or not isinstance(sample, int) or sample <= 0:
        return None
    return dict(value)


def estimate_headline(estimate: Any, exam: Any = None) -> str | None:
    """«≈ 62 балла ЕГЭ» for a test score, «отметка 4» for a grade."""
    normalized = normalized_estimate(estimate)
    if normalized is None:
        return None
    number = int(normalized["value"])
    if normalized["kind"] == "grade":
        return f"отметка {number}"
    unit = _plural(number, "балл", "балла", "баллов")
    exam_name = str(exam).strip() if isinstance(exam, str) and exam.strip() else ""
    return f"≈ {number} {unit} {exam_name}".strip()


def estimate_caption(estimate: Any) -> str | None:
    """«ориентировочно, по 12 заданиям»."""
    normalized = normalized_estimate(estimate)
    if normalized is None:
        return None
    sample = int(normalized["sample_size"])
    unit = _plural(sample, "заданию", "заданиям", "заданиям")
    return f"ориентировочно, по {sample} {unit}"
