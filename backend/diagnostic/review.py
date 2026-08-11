"""Private, immutable review snapshots for completed diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from diagnostic.catalog import (
    InputQuestion,
    MatchingQuestion,
    MultipleQuestion,
    Question,
    SingleQuestion,
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
        "is_correct",
        "user_answer",
        "expected_answer",
        "guidance",
        "guidance_kind",
    }
)


def format_answer(question: Question, answer: Any) -> str:
    if answer is None:
        return "Не отвечено"
    options = {option.id: option.label for option in getattr(question, "options", ())}
    if isinstance(question, SingleQuestion):
        return options.get(str(answer), str(answer))
    if isinstance(question, MultipleQuestion):
        values = answer if isinstance(answer, list) else []
        return ", ".join(options.get(str(value), str(value)) for value in values) or "Не отвечено"
    if isinstance(question, MatchingQuestion):
        values = answer if isinstance(answer, Mapping) else {}
        return "; ".join(
            f"{item.label}: {options.get(str(values.get(item.id, '')), 'Не отвечено')}"
            for item in question.items
        )
    if isinstance(question, InputQuestion) and isinstance(answer, (list, tuple)):
        return " / ".join(str(value) for value in answer)
    return str(answer)


def expected_value(question: Question) -> Any:
    return deepcopy(question.correct)


def fallback_guidance(question: Question, expected_answer: str) -> str:
    if isinstance(question, MultipleQuestion):
        return (
            f"Проверьте каждый вариант по теме «{question.topic}» отдельно и "
            f"перенесите весь набор: {expected_answer}."
        )
    if isinstance(question, MatchingQuestion):
        return (
            "Сопоставляйте строки по одной и сохраняйте исходный порядок. "
            f"Правильная схема: {expected_answer}."
        )
    if isinstance(question, SingleQuestion):
        return (
            f"Примените правило темы «{question.topic}», исключите противоречащие "
            f"условию варианты и выберите: {expected_answer}."
        )
    return (
        f"Решите задание по алгоритму темы «{question.topic}» и перенесите только "
        f"итоговое значение: {expected_answer}."
    )


def build_review_snapshot(
    questions: Sequence[Question], answers: Mapping[str, Any]
) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for number, question in enumerate(questions, start=1):
        user_value = deepcopy(answers.get(question.id))
        answer_value = expected_value(question)
        expected_answer = format_answer(question, answer_value)
        individual_guidance = question.explanation
        assets = getattr(question, "assets", None)
        snapshot.append(
            {
                "question_id": question.id,
                "number": number,
                "type": question.type,
                "topic": question.topic,
                "title": question.title,
                "prompt": question.prompt,
                "asset": question.asset,
                "assets": list(assets) if assets else None,
                "options": [
                    option.model_dump(mode="json")
                    for option in getattr(question, "options", ())
                ],
                "items": [
                    item.model_dump(mode="json")
                    for item in getattr(question, "items", ())
                ],
                "is_correct": is_answer_correct(question, user_value),
                "user_value": user_value,
                "expected_value": answer_value,
                "user_answer": format_answer(question, user_value),
                "expected_answer": expected_answer,
                "guidance": individual_guidance
                or fallback_guidance(question, expected_answer),
                "guidance_kind": "individual" if individual_guidance else "fallback",
            }
        )
    return snapshot


def public_review_items(report_snapshot: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    review_snapshot = report_snapshot.get("review_snapshot")
    if not isinstance(review_snapshot, list):
        return None
    return [
        {
            key: value
            for key, value in item.items()
            if key in _PUBLIC_REVIEW_FIELDS
        }
        for item in review_snapshot
        if isinstance(item, Mapping)
    ]
