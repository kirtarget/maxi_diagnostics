"""Server-only answer checking and diagnostic result summaries."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from diagnostic.catalog import (
    DiagnosticCatalog,
    MatchingQuestion,
    MultipleQuestion,
    Question,
    SingleQuestion,
)
from diagnostic.numeric import normalize_numeric_answer


class TopicScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    topic: str
    correct_count: int = Field(ge=0)
    question_count: int = Field(gt=0)
    ratio: float = Field(ge=0, le=1)


class ScoreResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    diagnostic_id: str
    mode: Literal["quick", "full"]
    correct_count: int = Field(ge=0)
    question_count: int = Field(gt=0)
    score: int = Field(ge=0)
    max_score: int = Field(gt=0)
    score_unit: str
    strong_topics: tuple[TopicScore, ...]
    growth_topics: tuple[TopicScore, ...]


def score_answers(
    catalog: DiagnosticCatalog,
    diagnostic_id: str,
    mode: Literal["quick", "full"],
    answers: dict[str, Any],
) -> ScoreResult:
    questions = catalog.questions_for_mode(diagnostic_id, mode)
    diagnostic = catalog.get(diagnostic_id)
    if set(answers) - {question.id for question in questions}:
        raise ValueError("unknown_question")

    correct_by_question = {
        question.id: is_answer_correct(question, answers.get(question.id))
        for question in questions
    }
    correct_count = sum(correct_by_question.values())
    score = math.floor(
        (correct_count / len(questions)) * diagnostic.scoring.max_score + 0.5
    )
    topics = _topic_scores(questions, correct_by_question)
    strong_topics = [item for item in topics if item.ratio >= 0.7]
    growth_topics = [item for item in topics if item.ratio < 0.7]
    return ScoreResult(
        diagnostic_id=diagnostic.id,
        mode=mode,
        correct_count=correct_count,
        question_count=len(questions),
        score=score,
        max_score=diagnostic.scoring.max_score,
        score_unit=diagnostic.scoring.score_unit,
        strong_topics=tuple(
            sorted(strong_topics, key=lambda item: (-item.ratio, item.topic.casefold()))[:2]
        ),
        growth_topics=tuple(
            sorted(growth_topics, key=lambda item: (item.ratio, item.topic.casefold()))[:2]
        ),
    )


def is_answer_correct(question: Question, answer: Any) -> bool:
    if isinstance(question, SingleQuestion):
        return isinstance(answer, str) and answer == question.correct
    if isinstance(question, MultipleQuestion):
        return isinstance(answer, list) and sorted(answer) == sorted(question.correct)
    if isinstance(question, MatchingQuestion):
        return isinstance(answer, dict) and answer == question.correct
    normalized_answer = _normalize_decimal(answer)
    return normalized_answer is not None and any(
        normalized_answer == _normalize_decimal(variant) for variant in question.correct
    )


def _normalize_decimal(value: Any) -> Decimal | None:
    return normalize_numeric_answer(value)


def _topic_scores(
    questions: tuple[Question, ...], correct_by_question: dict[str, bool]
) -> list[TopicScore]:
    totals: dict[str, list[int]] = {}
    for question in questions:
        correct, total = totals.setdefault(question.topic, [0, 0])
        totals[question.topic] = [
            correct + int(correct_by_question[question.id]),
            total + 1,
        ]
    return [
        TopicScore(
            topic=topic,
            correct_count=correct,
            question_count=total,
            ratio=correct / total,
        )
        for topic, (correct, total) in totals.items()
    ]
