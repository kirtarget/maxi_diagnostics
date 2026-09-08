"""Private, immutable review snapshots for completed diagnostics."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from diagnostic.catalog import (
    InputQuestion,
    is_skipped_answer,
    MatchingQuestion,
    MultipleQuestion,
    Question,
    SingleQuestion,
    TextQuestion,
)
from diagnostic.scoring import is_answer_correct


_PUBLIC_REVIEW_FIELDS = frozenset(
    {
        "question_id",
        "number",
        "type",
        "topic",
        "title",
        "prompt",
        "asset",
        "assets",
        "asset_alt",
        "is_correct",
        "status",
        "max_primary_score",
        "earned_primary_score",
        "source",
        "user_answer",
        "expected_answer",
        "guidance",
        "guidance_kind",
        "learning_material_text",
        "answer_preview",
    }
)


def format_answer(question: Question, answer: Any) -> str:
    if answer is None:
        return "Не отвечено"
    options = {option.id: option.label for option in getattr(question, "options", ())}
    if isinstance(question, SingleQuestion):
        return options.get(str(answer), str(answer))
    if isinstance(question, MultipleQuestion):
        values = answer if isinstance(answer, (list, tuple, set, frozenset)) else []
        return ", ".join(options.get(str(value), str(value)) for value in values) or "Не отвечено"
    if isinstance(question, MatchingQuestion):
        values = answer if isinstance(answer, Mapping) else {}
        return "; ".join(
            f"{item.label}: {options.get(str(values.get(item.id, '')), 'Не отвечено')}"
            for item in question.items
        )
    if isinstance(question, (InputQuestion, TextQuestion)) and isinstance(answer, (list, tuple)):
        return " / ".join(str(value) for value in answer)
    return str(answer)


def expected_value(question: Question) -> Any:
    return deepcopy(question.correct)


_DISPLAY_LETTER_MARKER = re.compile(r"^\s*([А-ЯЁA-Z]+)(?:[).]|\s|$)")
_DISPLAY_NUMBER_MARKER = re.compile(r"^\s*(\d{1,2})[).]")


def _marker(label: str, fallback: str) -> str:
    match = _DISPLAY_LETTER_MARKER.match(label) or _DISPLAY_NUMBER_MARKER.match(label)
    return match.group(1) if match else fallback


def _structured_answer_preview(
    question: Question, user_value: Any, expected_value_: Any,
) -> dict[str, Any] | None:
    """Return display-only selections for the shared review renderer.

    IDs never cross this seam. The preview contains only source display markers,
    user selections, and the already-authorized expected selections.
    """
    if isinstance(question, MatchingQuestion):
        option_markers = {
            option.id: _marker(option.label, str(index + 1))
            for index, option in enumerate(question.options)
        }
        row_markers = [
            _marker(item.label, str(index + 1))
            for index, item in enumerate(question.items)
        ]
        user_map = user_value if isinstance(user_value, Mapping) else {}
        expected_map = expected_value_ if isinstance(expected_value_, Mapping) else {}
        return {
            "kind": "matching",
            "markers": row_markers,
            "user": [option_markers.get(str(user_map.get(item.id, "")), "") for item in question.items],
            "expected": [option_markers.get(str(expected_map.get(item.id, "")), "") for item in question.items],
        }
    if isinstance(question, MultipleQuestion):
        markers = [
            _marker(option.label, chr(ord("A") + index))
            for index, option in enumerate(question.options)
        ]
        option_markers = {option.id: markers[index] for index, option in enumerate(question.options)}
        user_values = user_value if isinstance(user_value, (list, tuple, set, frozenset)) else ()
        expected_values = expected_value_ if isinstance(expected_value_, (list, tuple, set, frozenset)) else ()
        return {
            "kind": "multiple",
            "markers": markers,
            "user": [option_markers[str(value)] for value in user_values if str(value) in option_markers],
            "expected": [option_markers[str(value)] for value in expected_values if str(value) in option_markers],
        }
    if isinstance(question, InputQuestion) and question.answer_format == "sequence":
        markers = list(question.markers or ())
        user = list(user_value) if isinstance(user_value, str) else []
        expected = list(expected_value_) if isinstance(expected_value_, (list, tuple, str)) else []
        return {"kind": "sequence", "markers": markers, "user": user, "expected": expected}
    return None


def fallback_guidance(question: Question, expected_answer: str) -> str:
    """Return an honest placeholder until a verified study-book text is stored.

    A generic algorithm based on question type looks useful, but it is not a
    source-backed explanation for this particular task.  Do not fabricate one.
    """
    del question, expected_answer
    return "Подтверждённый разбор в учебнике MAXIMUM для этого задания пока не добавлен."


def build_review_snapshot(
    questions: Sequence[Question], answers: Mapping[str, Any]
) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for number, question in enumerate(questions, start=1):
        user_value = deepcopy(answers.get(question.id))
        answer_value = expected_value(question)
        expected_answer = format_answer(question, answer_value)
        individual_guidance = question.explanation
        is_correct = is_answer_correct(question, user_value)
        skipped = is_skipped_answer(question, user_value)
        assets = getattr(question, "assets", None)
        item = {
                "question_id": question.id,
                "number": number,
                "type": question.type,
                "topic": question.topic,
                "title": question.title,
                "prompt": question.prompt,
                "asset": question.asset,
                "assets": list(assets) if assets else None,
                "asset_alt": getattr(question, "asset_alt", None),
                "options": [
                    option.model_dump(mode="json")
                    for option in getattr(question, "options", ())
                ],
                "items": [
                    item.model_dump(mode="json")
                    for item in getattr(question, "items", ())
                ],
                "is_correct": is_correct,
                "status": "skipped" if skipped else "correct" if is_correct else "incorrect",
                "max_primary_score": question.max_primary_score,
                "earned_primary_score": question.max_primary_score if is_correct else 0,
                "source": (
                    question.source.model_dump(mode="json")
                    if question.source is not None
                    else None
                ),
                "user_value": user_value,
                "expected_value": answer_value,
                "user_answer": (
                    "Ты пропустил задание"
                    if skipped
                    else format_answer(question, user_value)
                ),
                "expected_answer": expected_answer,
                "guidance": individual_guidance
                or fallback_guidance(question, expected_answer),
                "guidance_kind": "individual" if individual_guidance else "fallback",
                "learning_material_text": question.learning_material_text,
                "learning_material_url": question.learning_material_url,
            }
        preview = _structured_answer_preview(question, user_value, answer_value)
        if preview is not None:
            item["answer_preview"] = preview
        snapshot.append(item)
    return snapshot


def public_review_items(report_snapshot: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    review_snapshot = report_snapshot.get("review_snapshot")
    if not isinstance(review_snapshot, list):
        return None
    public_items: list[dict[str, Any]] = []
    for item in review_snapshot:
        if not isinstance(item, Mapping):
            continue
        public_item = {
            key: value for key, value in item.items() if key in _PUBLIC_REVIEW_FIELDS
        }
        public_item.setdefault(
            "status", "correct" if public_item.get("is_correct") else "incorrect"
        )
        if (
            public_item.get("expected_answer") == "Не отвечено"
            and not item.get("expected_value")
        ):
            public_item["expected_answer"] = "Эталонный ответ не сохранён"
        public_items.append(public_item)
    return public_items
