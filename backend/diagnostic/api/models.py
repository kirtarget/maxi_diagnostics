"""Bounded request models for the public Mini App API."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    init_data: str = Field(min_length=1, max_length=16384)


class SessionRequest(ApiRequest):
    attempt_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,48}$")
    session_scope: str = Field(pattern=r"^[0-9a-f]{24}$")


class ProgressRequest(SessionRequest):
    supersedes_attempt_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_-]{8,48}$"
    )
    diagnostic_id: str = Field(min_length=3, max_length=64)
    content_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["quick", "full"]
    question_index: int = Field(ge=0, le=200, strict=True)
    question_count: int = Field(ge=1, le=200, strict=True)
    progress_revision: int = Field(ge=1, le=1000, strict=True)
    answers: dict[str, Any]

    @model_validator(mode="after")
    def validate_answers_size(self) -> "ProgressRequest":
        _validate_answers_size(self.answers)
        return self


class CompletionRequest(SessionRequest):
    supersedes_attempt_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_-]{8,48}$"
    )
    diagnostic_id: str = Field(min_length=3, max_length=64)
    content_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["quick", "full"]
    question_count: int = Field(ge=1, le=200, strict=True)
    progress_revision: int = Field(ge=1, le=1000, strict=True)
    answers: dict[str, Any]

    @model_validator(mode="after")
    def validate_answers_size(self) -> "CompletionRequest":
        _validate_answers_size(self.answers)
        return self


class TrainerStartRequest(ApiRequest):
    session_scope: str = Field(pattern=r"^[0-9a-f]{24}$")
    diagnostic_id: str = Field(min_length=3, max_length=64)
    count: int = Field(ge=1, le=200, strict=True)
    topic: str | None = Field(default=None, min_length=1, max_length=128)
    mode: Literal["normal", "mistakes"] = "normal"
    source_attempt_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_-]{8,48}$"
    )


class TrainerAnswerRequest(ApiRequest):
    session_scope: str = Field(pattern=r"^[0-9a-f]{24}$")
    trainer_session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{32,64}$")
    question_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    answer: Any
    revision: int = Field(ge=1, le=100000, strict=True)
    idempotency_key: str | None = Field(
        default=None, min_length=1, max_length=128,
        pattern=r"^[A-Za-z0-9:_-]{1,128}$",
    )

    @model_validator(mode="after")
    def validate_answer_size(self) -> "TrainerAnswerRequest":
        try:
            encoded = json.dumps(
                self.answer, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("answer_not_serializable") from exc
        if len(encoded) > 16384:
            raise ValueError("answer_too_large")
        return self


class TrainerFinishRequest(ApiRequest):
    session_scope: str = Field(pattern=r"^[0-9a-f]{24}$")
    trainer_session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{32,64}$")
    revision: int = Field(ge=1, le=100000, strict=True)


class OfferEventRequest(ApiRequest):
    session_scope: str = Field(pattern=r"^[0-9a-f]{24}$")
    event_id: str = Field(
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]{16,128}$",
    )
    placement: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z][a-z0-9_-]{0,31}$",
    )
    offer_id: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$",
    )
    event_type: Literal["impression", "click", "dismiss"]


def _validate_answers_size(answers: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(answers, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("answers_not_serializable") from exc
    if len(encoded) > 64000:
        raise ValueError("answers_too_large")
