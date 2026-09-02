"""Shared estimate wording, and the PDF and bot surfaces that use it."""

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader

from diagnostic.catalog import load_catalog
from diagnostic.review import build_review_snapshot
from diagnostic.school import load_school
from diagnostic.score_text import estimate_caption, estimate_headline

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHOOL = ROOT / "tests/fixtures/sample-school"


def estimate(**overrides) -> dict:
    return {
        "kind": "test_score",
        "value": 62,
        "scaled_primary": 24,
        "exam_max_primary": 45,
        "sample_max_primary": 12,
        "sample_size": 12,
        "min_pass": 36,
    } | overrides


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, "≈ 1 балл ЕГЭ"),
        (2, "≈ 2 балла ЕГЭ"),
        (11, "≈ 11 баллов ЕГЭ"),
        (62, "≈ 62 балла ЕГЭ"),
        (100, "≈ 100 баллов ЕГЭ"),
    ],
)
def test_headline_declines_the_point_noun(value: int, expected: str):
    assert estimate_headline(estimate(value=value), "ЕГЭ") == expected


def test_headline_names_the_grade_without_an_exam():
    assert estimate_headline(estimate(kind="grade", value=4), "ОГЭ") == "отметка 4"


def test_headline_drops_a_missing_exam_name():
    assert estimate_headline(estimate(value=62), None) == "≈ 62 балла"


@pytest.mark.parametrize(
    ("sample", "expected"),
    [(1, "ориентировочно, по 1 заданию"), (12, "ориентировочно, по 12 заданиям")],
)
def test_caption_reports_the_sample_size(sample: int, expected: str):
    assert estimate_caption(estimate(sample_size=sample)) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"kind": "test_score", "value": 62},
        {"kind": "unknown", "value": 62, "sample_size": 12},
        {"kind": "test_score", "value": "62", "sample_size": 12},
        {"kind": "test_score", "value": True, "sample_size": 12},
        {"kind": "test_score", "value": 62, "sample_size": 0},
        "estimate",
    ],
)
def test_wording_is_absent_for_an_unusable_estimate(value):
    assert estimate_headline(value, "ЕГЭ") is None
    assert estimate_caption(value) is None


def pdf_text(attempt) -> str:
    from diagnostic.report import build_report

    pdf = build_report(attempt, load_school(SAMPLE_SCHOOL))
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)


def premium_attempt(result_snapshot: dict) -> dict:
    from tests.test_report import completed_attempt, make_review_report_snapshot

    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    review_snapshot = build_review_snapshot(
        diagnostic.questions, completed_attempt()["answers"]
    )
    return completed_attempt(
        report_snapshot=make_review_report_snapshot(school, diagnostic, review_snapshot),
        result_snapshot=result_snapshot,
    )


def test_premium_report_shows_the_estimate_and_its_caption():
    text = pdf_text(
        premium_attempt({"score": 100, "estimate": estimate(kind="grade", value=4)})
    )

    assert "отметка 4" in text
    assert "ориентировочно, по 12 заданиям" in text


def test_premium_report_omits_the_estimate_block_for_an_older_attempt():
    text = pdf_text(premium_attempt({"score": 100}))

    assert "ориентировочно" not in text
    assert "Текущий результат" in text
