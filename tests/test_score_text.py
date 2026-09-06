"""Shared estimate wording used by the bot and the Mini App."""

import pytest

from diagnostic.score_text import estimate_caption, estimate_headline


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
