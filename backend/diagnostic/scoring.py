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
    TextQuestion,
)
from diagnostic.numeric import normalize_numeric_answer
from diagnostic.text_answers import is_valid_text_answer, normalize_text_answer
from diagnostic.school import GradeScale, TestScoreScale


ScoreScale = TestScoreScale | GradeScale


def round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


class TopicScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    topic: str
    correct_count: int = Field(ge=0)
    question_count: int = Field(gt=0)
    ratio: float = Field(ge=0, le=1)
    primary_score: int = Field(ge=0)
    max_primary_score: int = Field(gt=0)


class ScoreEstimate(BaseModel):
    """Official-scale estimate projected from a short sample of exam tasks."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["test_score", "grade"]
    value: int = Field(ge=0)
    scaled_primary: int = Field(ge=0)
    exam_max_primary: int = Field(gt=0)
    sample_max_primary: int = Field(gt=0)
    sample_size: int = Field(gt=0)
    min_pass: int | None = None


def estimate_for_primary(
    scale: ScoreScale,
    primary_score: int,
    sample_max_primary: int,
    sample_size: int,
) -> ScoreEstimate:
    """Project a sample primary score onto the full exam scale. Pure."""
    if sample_max_primary <= 0 or sample_size <= 0:
        raise ValueError("invalid_score_sample")
    bounded = min(max(primary_score, 0), sample_max_primary)
    scaled_primary = min(
        round_half_up(bounded / sample_max_primary * scale.max_primary),
        scale.max_primary,
    )
    return ScoreEstimate(
        kind=scale.kind,
        value=scale.value_for(scaled_primary),
        scaled_primary=scaled_primary,
        exam_max_primary=scale.max_primary,
        sample_max_primary=sample_max_primary,
        sample_size=sample_size,
        min_pass=scale.min_pass,
    )


class ScoreResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    diagnostic_id: str
    mode: Literal["quick", "full"]
    correct_count: int = Field(ge=0)
    question_count: int = Field(gt=0)
    primary_score: int = Field(ge=0)
    max_primary_score: int = Field(gt=0)
    score: int = Field(ge=0)
    max_score: int = Field(gt=0)
    score_unit: str
    strong_topics: tuple[TopicScore, ...]
    growth_topics: tuple[TopicScore, ...]
    recoverable_primary_score: int = Field(default=0, ge=0)
    estimate: ScoreEstimate | None = None


def score_answers(
    catalog: DiagnosticCatalog,
    diagnostic_id: str,
    mode: Literal["quick", "full"],
    answers: dict[str, Any],
    scale: ScoreScale | None = None,
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
    primary_score = sum(
        question.max_primary_score
        for question in questions
        if correct_by_question[question.id]
    )
    max_primary_score = sum(question.max_primary_score for question in questions)
    score = math.floor(
        (primary_score / max_primary_score) * diagnostic.scoring.max_score + 0.5
    )
    topics = _topic_scores(questions, correct_by_question)
    strong_topics = sorted(
        (item for item in topics if item.ratio >= 0.7),
        key=lambda item: (-item.ratio, item.topic.casefold()),
    )[:2]
    growth_topics = sorted(
        (item for item in topics if item.ratio < 0.7),
        key=lambda item: (item.ratio, item.topic.casefold()),
    )[:2]
    return ScoreResult(
        diagnostic_id=diagnostic.id,
        mode=mode,
        correct_count=correct_count,
        question_count=len(questions),
        primary_score=primary_score,
        max_primary_score=max_primary_score,
        score=score,
        max_score=diagnostic.scoring.max_score,
        score_unit=diagnostic.scoring.score_unit,
        strong_topics=tuple(strong_topics),
        growth_topics=tuple(growth_topics),
        recoverable_primary_score=sum(
            item.max_primary_score - item.primary_score for item in growth_topics
        ),
        estimate=(
            estimate_for_primary(
                scale, primary_score, max_primary_score, len(questions)
            )
            if scale is not None else None
        ),
    )


def is_answer_correct(question: Question, answer: Any) -> bool:
    if isinstance(question, SingleQuestion):
        return isinstance(answer, str) and answer == question.correct
    if isinstance(question, MultipleQuestion):
        return isinstance(answer, list) and sorted(answer) == sorted(question.correct)
    if isinstance(question, MatchingQuestion):
        return isinstance(answer, dict) and answer == question.correct
    if isinstance(question, TextQuestion):
        if not is_valid_text_answer(answer, question.max_length):
            return False
        normalized_text = normalize_text_answer(answer)
        return any(
            normalized_text == normalize_text_answer(variant)
            for variant in question.correct
        )
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
        correct, total, earned, maximum = totals.setdefault(
            question.topic, [0, 0, 0, 0]
        )
        is_correct = correct_by_question[question.id]
        totals[question.topic] = [
            correct + int(is_correct),
            total + 1,
            earned + (question.max_primary_score if is_correct else 0),
            maximum + question.max_primary_score,
        ]
    return [
        TopicScore(
            topic=topic,
            correct_count=correct,
            question_count=total,
            ratio=earned / maximum,
            primary_score=earned,
            max_primary_score=maximum,
        )
        for topic, (correct, total, earned, maximum) in totals.items()
    ]
