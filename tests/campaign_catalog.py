"""Read catalog files the way the fipi-2026-min15 campaign owns them.

Later imports append questions from other providers to the same files. The
campaign guardrails only describe the baseline and its own draft slots, so the
helpers here drop those appended questions and assert they never appear before
a campaign-scope one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CAMPAIGN_SCOPE_PROVIDERS = frozenset({None, "maximum"})


def is_external(question: dict[str, Any]) -> bool:
    source = question.get("source")
    provider = source.get("provider") if isinstance(source, dict) else None
    return provider not in CAMPAIGN_SCOPE_PROVIDERS


def campaign_questions(document: dict[str, Any]) -> list[dict[str, Any]]:
    questions = document["questions"]
    scoped = [question for question in questions if not is_external(question)]
    assert questions[: len(scoped)] == scoped, "external additions must be appended"
    return scoped


def load_campaign_catalog(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    document = json.loads(raw.decode("utf-8"))
    return {**document, "questions": campaign_questions(document)}
