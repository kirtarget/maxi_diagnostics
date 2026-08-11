"""Validated, school-owned diagnostic question catalogs."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel, ConfigDict, Field, PrivateAttr, ValidationError,
    field_validator, model_validator,
)

from diagnostic.font_support import validate_report_text
from diagnostic.school import SchoolConfig, validate_asset_inventory, validate_asset_path
from diagnostic.jsonutil import load_json_file
from diagnostic.numeric import is_valid_numeric_answer


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
_ID_FULLMATCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_MAX_CATALOG_FILE_BYTES = 1024 * 1024
_MAX_TOTAL_CATALOG_BYTES = 5 * 1024 * 1024
_MAX_PUBLIC_PAYLOAD_BYTES = 2 * 1024 * 1024
_MAX_DIAGNOSTICS = 20
_MAX_QUESTIONS = 200
_MAX_TOTAL_QUESTIONS = 200
_MAX_OPTIONS = 50
_CATALOG_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.[Jj][Ss][Oo][Nn]\Z")
_WINDOWS_RESERVED_BASENAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)


def _validate_display_text(value: str) -> str:
    if not value.strip():
        raise ValueError("blank_text")
    if any(
        unicodedata.category(character).startswith("C")
        or unicodedata.category(character) in {"Zl", "Zp"}
        for character in value
    ):
        raise ValueError("unsafe_text")
    return validate_report_text(value)


class QuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=_ID_PATTERN)
    label: str = Field(min_length=1, max_length=500)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if _ID_FULLMATCH.fullmatch(value) is None:
            raise ValueError("invalid_identifier")
        return value

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        return _validate_display_text(value)


class QuestionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=_ID_PATTERN)
    type: str
    topic: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=4000)
    asset: str | None = Field(default=None, max_length=255)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if _ID_FULLMATCH.fullmatch(value) is None:
            raise ValueError("invalid_identifier")
        return value

    @field_validator("topic", "title", "prompt")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _validate_display_text(value)

    @model_validator(mode="after")
    def validate_optional_asset(self) -> "QuestionBase":
        if self.asset:
            validate_asset_path(self.asset)
        return self


class SingleQuestion(QuestionBase):
    type: Literal["single"]
    options: tuple[QuestionOption, ...] = Field(min_length=1, max_length=_MAX_OPTIONS)
    correct: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_correct_option(self) -> "SingleQuestion":
        _validate_unique_option_ids(self.options)
        if self.correct not in {option.id for option in self.options}:
            raise ValueError("invalid_option_reference")
        return self


class MultipleQuestion(QuestionBase):
    type: Literal["multiple"]
    options: tuple[QuestionOption, ...] = Field(min_length=1, max_length=_MAX_OPTIONS)
    selection_limit: int = Field(ge=1, le=_MAX_OPTIONS, strict=True)
    correct: tuple[str, ...] = Field(min_length=1, max_length=_MAX_OPTIONS)

    @model_validator(mode="after")
    def validate_multiple_options(self) -> "MultipleQuestion":
        _validate_unique_option_ids(self.options)
        option_ids = {option.id for option in self.options}
        if self.selection_limit > len(self.options) or len(self.correct) != self.selection_limit:
            raise ValueError("invalid_selection_limit")
        if len(set(self.correct)) != len(self.correct):
            raise ValueError("duplicate_correct_option")
        if not set(self.correct).issubset(option_ids):
            raise ValueError("invalid_option_reference")
        return self


class MatchingQuestion(QuestionBase):
    type: Literal["matching"]
    items: tuple[QuestionOption, ...] = Field(min_length=1, max_length=_MAX_OPTIONS)
    options: tuple[QuestionOption, ...] = Field(min_length=1, max_length=_MAX_OPTIONS)
    correct: dict[str, str] = Field(min_length=1, max_length=_MAX_OPTIONS)

    @model_validator(mode="after")
    def validate_matching_options(self) -> "MatchingQuestion":
        _validate_unique_option_ids(self.items)
        _validate_unique_option_ids(self.options)
        if set(self.correct) != {item.id for item in self.items}:
            raise ValueError("incomplete_matching_keys")
        if not set(self.correct.values()).issubset({option.id for option in self.options}):
            raise ValueError("invalid_option_reference")
        return self


class InputQuestion(QuestionBase):
    type: Literal["input"]
    correct: tuple[str, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_input_variants(self) -> "InputQuestion":
        for variant in self.correct:
            if not is_valid_numeric_answer(variant):
                raise ValueError("invalid_input_variant")
        return self


Question = Annotated[
    SingleQuestion | MultipleQuestion | MatchingQuestion | InputQuestion,
    Field(discriminator="type"),
]


class ScoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_score: Literal[100]
    score_unit: Literal["accuracy_percent"]


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3, max_length=64, pattern=_ID_PATTERN)
    exam: str = Field(min_length=1, max_length=32)
    subject: str = Field(min_length=1, max_length=128)
    mark: str = Field(min_length=1, max_length=128)
    quick_count: int = Field(ge=1, le=_MAX_QUESTIONS, strict=True)
    scoring: ScoringConfig
    questions: tuple[Question, ...] = Field(min_length=1, max_length=_MAX_QUESTIONS)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if _ID_FULLMATCH.fullmatch(value) is None:
            raise ValueError("invalid_identifier")
        return value

    @field_validator("exam", "subject", "mark")
    @classmethod
    def validate_labels(cls, value: str) -> str:
        return _validate_display_text(value)

    @model_validator(mode="after")
    def validate_questions(self) -> "Diagnostic":
        question_ids = [question.id for question in self.questions]
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("duplicate_question_id")
        if self.quick_count > len(self.questions):
            raise ValueError("invalid_quick_count")
        return self


def _public_diagnostic(diagnostic: Diagnostic, content_version: str) -> dict[str, Any]:
    return {
        **diagnostic.model_dump(exclude={"questions", "scoring"}, mode="json"),
        "content_version": content_version,
        "questions": [
            {
                key: value
                for key, value in question.model_dump(
                    mode="json", exclude_none=True
                ).items()
                if key != "correct"
            }
            for question in diagnostic.questions
        ],
    }


class DiagnosticCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diagnostics: tuple[Diagnostic, ...] = Field(min_length=1, max_length=_MAX_DIAGNOSTICS)
    _asset_digests: dict[str, str] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def validate_diagnostic_ids(self) -> "DiagnosticCatalog":
        diagnostic_ids = [diagnostic.id for diagnostic in self.diagnostics]
        if len(set(diagnostic_ids)) != len(diagnostic_ids):
            raise ValueError("duplicate_diagnostic_id")
        if sum(len(diagnostic.questions) for diagnostic in self.diagnostics) > _MAX_TOTAL_QUESTIONS:
            raise ValueError("too_many_total_questions")
        preview = {
            "diagnostics": [
                _public_diagnostic(diagnostic, "0" * 64)
                for diagnostic in self.diagnostics
            ]
        }
        encoded = json.dumps(
            preview, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded) > _MAX_PUBLIC_PAYLOAD_BYTES:
            raise ValueError("catalog_public_payload_too_large")
        return self

    def get(self, diagnostic_id: str) -> Diagnostic:
        for diagnostic in self.diagnostics:
            if diagnostic.id == diagnostic_id:
                return diagnostic
        raise ValueError("diagnostic_not_found")

    def questions_for_mode(
        self, diagnostic_id: str, mode: Literal["quick", "full"]
    ) -> tuple[Question, ...]:
        diagnostic = self.get(diagnostic_id)
        if mode == "quick":
            return diagnostic.questions[: diagnostic.quick_count]
        if mode == "full":
            return diagnostic.questions
        raise ValueError("invalid_mode")

    def public_payload(self, version_secret: str) -> dict[str, Any]:
        return {
            "diagnostics": [
                _public_diagnostic(
                    diagnostic, self.content_version(diagnostic.id, version_secret)
                )
                for diagnostic in self.diagnostics
            ]
        }

    def content_version(self, diagnostic_id: str, version_secret: str) -> str:
        diagnostic = self.get(diagnostic_id)
        private_payload = {
            "diagnostic": diagnostic.model_dump(mode="json"),
            "assets": {
                question.asset: self._asset_digests.get(question.asset, "")
                for question in diagnostic.questions
                if question.asset
            },
        }
        encoded = json.dumps(
            private_payload, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(version_secret.encode("utf-8"), encoded, hashlib.sha256).hexdigest()


def _validate_unique_option_ids(options: tuple[QuestionOption, ...]) -> None:
    if len({option.id for option in options}) != len(options):
        raise ValueError("duplicate_option_id")


def public_question(question: Question) -> dict[str, Any]:
    return {
        key: value
        for key, value in question.model_dump(mode="json", exclude_none=True).items()
        if key != "correct"
    }


def _validate_catalog_filenames(names: list[str]) -> None:
    folded: set[str] = set()
    for name in names:
        if (
            _CATALOG_FILENAME.fullmatch(name) is None
            or name.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_BASENAMES
        ):
            raise ValueError("catalog_unexpected_entry")
        canonical = name.casefold()
        if canonical in folded:
            raise ValueError("catalog_filename_collision")
        folded.add(canonical)


def _catalog_paths(diagnostics_root) -> tuple:
    if not diagnostics_root.is_dir() or diagnostics_root.is_symlink():
        raise ValueError("diagnostics_directory_not_found")
    entries = tuple(diagnostics_root.iterdir())
    for path in entries:
        if path.is_symlink():
            raise ValueError("catalog_symlink_not_allowed")
    _validate_catalog_filenames([path.name for path in entries])
    if any(not path.is_file() for path in entries):
        raise ValueError("catalog_unexpected_entry")
    if len(entries) > _MAX_DIAGNOSTICS:
        raise ValueError("too_many_diagnostics")
    total_bytes = 0
    for path in entries:
        size = path.stat().st_size
        if size > _MAX_CATALOG_FILE_BYTES:
            raise ValueError(f"catalog_file_too_large:{path.name}")
        total_bytes += size
    if total_bytes > _MAX_TOTAL_CATALOG_BYTES:
        raise ValueError("catalog_total_too_large")
    return tuple(sorted(entries, key=lambda path: path.name.casefold()))


def load_catalog(school: SchoolConfig) -> DiagnosticCatalog:
    diagnostics_root = school.resolve_asset("diagnostics")
    paths = _catalog_paths(diagnostics_root)
    diagnostics = []
    for path in paths:
        try:
            diagnostic = Diagnostic.model_validate(
                load_json_file(path, max_bytes=_MAX_CATALOG_FILE_BYTES)
            )
        except ValidationError:
            raise ValueError(f"catalog_invalid:{path.name}") from None
        for question in diagnostic.questions:
            if question.asset and not school.resolve_asset(question.asset).is_file():
                raise ValueError("question_asset_not_found")
        diagnostics.append(diagnostic)
    if not diagnostics:
        raise ValueError("diagnostics_not_found")
    catalog = DiagnosticCatalog(diagnostics=tuple(diagnostics))
    references = [school.brand.logo]
    references.extend(
        question.asset
        for diagnostic in catalog.diagnostics
        for question in diagnostic.questions
        if question.asset
    )
    validate_asset_inventory(school.root, references)
    catalog._asset_digests = {
        relative: hashlib.sha256(school.resolve_asset(relative).read_bytes()).hexdigest()
        for relative in set(references)
        if relative != school.brand.logo
    }
    return catalog
