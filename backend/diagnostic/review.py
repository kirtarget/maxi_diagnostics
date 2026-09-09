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
_PREVIEW_KINDS = frozenset({"matching", "multiple", "sequence"})
_PREVIEW_MAX_ENTRIES = 20
_PREVIEW_MAX_TEXT = 500


def format_answer(question: Question, answer: Any) -> str:
    if answer is None:
        return "Не отвечено"
    options = {option.id: option.label for option in getattr(question, "options", ())}
    if isinstance(question, SingleQuestion):
        option = next((option for option in question.options if option.id == answer), None)
        if option is not None and option.stress:
            return f"{option.label} · ударение: {option.stress}"
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


# The KIM prints Cyrillic positions and skips Ё. The mini app draws these same
# markers, so the review has to name a position the way the screen did.
_POSITION_MARKERS = ("А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К", "Л", "М")
# Latin letters an editor typed where the KIM prints Cyrillic. B is the shape of
# В, not of Б, which has no Latin lookalike at all.
_LOOKALIKE_CYRILLIC = {
    "A": "А", "B": "В", "C": "С", "E": "Е", "K": "К", "M": "М",
    "H": "Н", "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
}


def _marker(label: str, fallback: str) -> str:
    match = _DISPLAY_LETTER_MARKER.match(label) or _DISPLAY_NUMBER_MARKER.match(label)
    return match.group(1) if match else fallback


def _position_marker(label: str, index: int) -> str:
    """Name a matching position exactly as the answer editor draws it."""
    fallback = _POSITION_MARKERS[index] if index < len(_POSITION_MARKERS) else str(index + 1)
    marker = _marker(label, fallback)
    return _LOOKALIKE_CYRILLIC.get(marker, marker)


def _sequence_option_labels(prompt: str) -> dict[str, str]:
    """Extract the display labels from the dedicated source word list."""
    labels: dict[str, str] = {}
    in_word_list = False
    for line in prompt.splitlines():
        normalized = line.strip()
        if re.search(r"\bсписок\s+слов\b", normalized, re.IGNORECASE):
            in_word_list = True
            continue
        if in_word_list and re.match(r"^(?:в\s+ответ|введите)\b", normalized, re.IGNORECASE):
            break
        if not in_word_list:
            continue
        match = re.match(r"^\s*(\d{1,2})[).]\s*(.+?)\s*$", normalized)
        if match:
            labels[match.group(1)] = match.group(2).rstrip(";,. ")
    return labels


def _structured_answer_preview(
    question: Question, user_value: Any, expected_value_: Any,
) -> dict[str, Any] | None:
    """Return display-only selections for the shared review renderer.

    IDs never cross this seam. The preview contains only source display markers,
    user selections, and the already-authorized expected selections.
    """
    if isinstance(question, MatchingQuestion):
        option_markers: dict[str, str] = {}
        option_labels: dict[str, str] = {}
        used_markers: set[str] = set()
        for index, option in enumerate(question.options):
            marker = _marker(option.label, str(index + 1))
            if marker in used_markers:
                marker = str(index + 1)
                while marker in used_markers:
                    marker = str(int(marker) + 1)
            used_markers.add(marker)
            option_markers[option.id] = marker
            option_labels[marker] = option.label
        row_markers = [
            _position_marker(item.label, index)
            for index, item in enumerate(question.items)
        ]
        user_map = user_value if isinstance(user_value, Mapping) else {}
        expected_map = expected_value_ if isinstance(expected_value_, Mapping) else {}
        return {
            "kind": "matching",
            "markers": row_markers,
            "user": [option_markers.get(str(user_map.get(item.id, "")), "") for item in question.items],
            "expected": [option_markers.get(str(expected_map.get(item.id, "")), "") for item in question.items],
            "option_labels": option_labels,
        }
    if isinstance(question, MultipleQuestion):
        markers = [str(index + 1) for index, _ in enumerate(question.options)]
        option_markers = {option.id: markers[index] for index, option in enumerate(question.options)}
        user_values = user_value if isinstance(user_value, (list, tuple, set, frozenset)) else ()
        expected_values = expected_value_ if isinstance(expected_value_, (list, tuple, set, frozenset)) else ()
        return {
            "kind": "multiple",
            "markers": markers,
            "user": [option_markers[str(value)] for value in user_values if str(value) in option_markers],
            "expected": [option_markers[str(value)] for value in expected_values if str(value) in option_markers],
            "option_labels": {markers[index]: option.label for index, option in enumerate(question.options)},
        }
    if isinstance(question, InputQuestion) and question.answer_format == "sequence":
        markers = list(question.markers or ())
        user = list(user_value) if isinstance(user_value, str) else []
        if isinstance(expected_value_, str):
            expected = list(expected_value_)
        elif isinstance(expected_value_, (list, tuple)):
            expected = list(expected_value_[0]) if len(expected_value_) == 1 and isinstance(expected_value_[0], str) else list(expected_value_)
        else:
            expected = []
        return {
            "kind": "sequence",
            "markers": markers,
            "user": user,
            "expected": expected,
            "option_labels": _sequence_option_labels(question.prompt),
        }
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
                    option.model_dump(mode="json", exclude_none=True)
                    for option in getattr(question, "options", ())
                ],
                "items": [
                    item.model_dump(mode="json", exclude_none=True)
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
        preview = _sanitize_answer_preview(public_item.get("answer_preview"))
        if preview is None:
            public_item.pop("answer_preview", None)
        else:
            public_item["answer_preview"] = preview
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


def _sanitize_answer_preview(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or value.get("kind") not in _PREVIEW_KINDS:
        return None

    def strings(candidate: Any) -> list[str] | None:
        if not isinstance(candidate, (list, tuple)) or len(candidate) > _PREVIEW_MAX_ENTRIES:
            return None
        if any(not isinstance(entry, str) or len(entry) > _PREVIEW_MAX_TEXT for entry in candidate):
            return None
        return list(candidate)

    markers = strings(value.get("markers"))
    user = strings(value.get("user"))
    expected = strings(value.get("expected"))
    if markers is None or user is None or expected is None:
        return None
    option_labels: dict[str, str] = {}
    raw_labels = value.get("option_labels")
    if isinstance(raw_labels, Mapping):
        for key, label in list(raw_labels.items())[:_PREVIEW_MAX_ENTRIES]:
            if isinstance(key, str) and isinstance(label, str) and len(key) <= _PREVIEW_MAX_TEXT and len(label) <= _PREVIEW_MAX_TEXT:
                option_labels[key] = label
    return {
        "kind": value["kind"],
        "markers": markers,
        "user": user,
        "expected": expected,
        **({"option_labels": option_labels} if option_labels else {}),
    }
