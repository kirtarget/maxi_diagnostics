"""Official 2026 scale loading, validation and the estimate projected from it."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from diagnostic.catalog import load_catalog, validate_score_scale_coverage
from diagnostic import school as school_module
from diagnostic.school import SCORE_SCALES_ADAPTER, GradeScale, load_school
from diagnostic.scoring import estimate_for_primary

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCALES_PATH = REPOSITORY_ROOT / "school/score_scales.json"


def scale_payload(**overrides) -> dict:
    payload = {
        "id": "ege-demo",
        "exam": "ЕГЭ",
        "subject": "Демо",
        "kind": "test_score",
        "max_primary": 4,
        "min_pass": 36,
        "table": [0, 30, 60, 80, 100],
        "interpolated_primary": [],
        "notes": "",
        "source": {
            "title": "Источник",
            "url": "https://example.org/scale.pdf",
            "date": "2026-05-07",
            "confidence": "secondary",
        },
    }
    return payload | overrides


def grade_payload(**overrides) -> dict:
    payload = scale_payload()
    payload.pop("table")
    payload |= {
        "id": "oge-demo",
        "exam": "ОГЭ",
        "kind": "grade",
        "max_primary": 10,
        "min_pass": None,
        "grades": {"3": 3, "4": 6, "5": 9},
    }
    return payload | overrides


def load(*scales) -> tuple:
    return SCORE_SCALES_ADAPTER.validate_python({"scales": list(scales)}).scales


def test_published_scales_cover_every_diagnostic_exactly_once():
    school = load_school(REPOSITORY_ROOT / "school")
    catalog = load_catalog(school)

    pairs = [(scale.exam, scale.subject) for scale in school.scales]

    assert len(pairs) == len(set(pairs)) == len(catalog.diagnostics)
    for diagnostic in catalog.diagnostics:
        matching = [
            scale for scale in school.scales
            if (scale.exam, scale.subject) == (diagnostic.exam, diagnostic.subject)
        ]
        assert len(matching) == 1


def test_published_scales_are_bounded_and_monotonic():
    scales = load_school(REPOSITORY_ROOT / "school").scales

    for scale in scales:
        if isinstance(scale, school_module.TestScoreScale):
            assert len(scale.table) == scale.max_primary + 1
            assert scale.table[0] == 0
            assert scale.table[-1] == 100
            assert list(scale.table) == sorted(scale.table)
        else:
            assert scale.grades["3"] < scale.grades["4"] < scale.grades["5"]
            assert scale.grades["5"] <= scale.max_primary


def test_interpolated_cells_are_declared_and_sit_between_their_neighbours():
    raw = json.loads(SCALES_PATH.read_text(encoding="utf-8"))
    declared = {
        scale["id"]: scale["interpolated_primary"]
        for scale in raw["scales"]
        if scale["interpolated_primary"]
    }

    assert declared == {
        "ege-english-language": [29],
        "ege-literature": [14, 42, 43, 44],
        "ege-physics": [17],
    }
    for scale in raw["scales"]:
        table = scale.get("table", [])
        for primary in scale["interpolated_primary"]:
            assert table[primary - 1] <= table[primary] <= table[primary + 1]


def test_loader_rejects_table_length_mismatch():
    with pytest.raises(ValidationError):
        load(scale_payload(table=[0, 50, 100]))


def test_loader_rejects_non_monotonic_table():
    with pytest.raises(ValidationError):
        load(scale_payload(table=[0, 30, 20, 80, 100]))


def test_loader_rejects_table_value_above_hundred():
    with pytest.raises(ValidationError):
        load(scale_payload(table=[0, 30, 60, 80, 101]))


def test_loader_rejects_unknown_field():
    with pytest.raises(ValidationError):
        load(scale_payload(weight=1))


def test_loader_rejects_grades_that_do_not_ascend():
    with pytest.raises(ValidationError):
        load(grade_payload(grades={"3": 6, "4": 6, "5": 9}))


def test_loader_rejects_grade_threshold_above_max_primary():
    with pytest.raises(ValidationError):
        load(grade_payload(grades={"3": 3, "4": 6, "5": 11}))


def test_loader_rejects_table_on_a_grade_scale():
    with pytest.raises(ValidationError):
        load(grade_payload(table=[0, 1]))


def test_loader_rejects_interpolated_primary_outside_the_table():
    with pytest.raises(ValidationError):
        load(scale_payload(interpolated_primary=[9]))


def test_loader_rejects_duplicate_identifiers():
    with pytest.raises(ValidationError):
        load(scale_payload(), scale_payload(exam="ОГЭ"))


def test_loader_rejects_two_scales_for_one_subject():
    with pytest.raises(ValidationError):
        load(scale_payload(), scale_payload(id="ege-demo-2"))


def test_catalog_rejects_a_scale_without_a_diagnostic():
    school = load_school(REPOSITORY_ROOT / "school")
    catalog = load_catalog(school)
    orphan = school.model_copy(
        update={"scales": (*school.scales, load(scale_payload())[0])}
    )

    with pytest.raises(ValueError, match="score_scale_without_diagnostic"):
        validate_score_scale_coverage(orphan, catalog)


def test_estimate_maps_the_boundaries_of_a_test_score_scale():
    scale = load(scale_payload())[0]

    zero = estimate_for_primary(scale, 0, 8, 4)
    full = estimate_for_primary(scale, 8, 8, 4)

    assert (zero.value, zero.scaled_primary) == (0, 0)
    assert (full.value, full.scaled_primary) == (100, 4)
    assert full.exam_max_primary == 4
    assert full.sample_max_primary == 8
    assert full.sample_size == 4
    assert full.min_pass == 36
    assert full.kind == "test_score"


def test_estimate_rounds_the_scaled_primary_half_up():
    scale = load(scale_payload())[0]

    # 3/8 of 4 primary points is 1.5, which rounds up to 2.
    assert estimate_for_primary(scale, 3, 8, 4).scaled_primary == 2


def test_estimate_reads_an_interpolated_cell_like_any_other():
    physics = next(
        scale for scale in load_school(REPOSITORY_ROOT / "school").scales
        if scale.id == "ege-physics"
    )

    estimate = estimate_for_primary(physics, 17, physics.max_primary, 20)

    assert estimate.scaled_primary == 17
    assert estimate.value == 53
    assert physics.table[16] < estimate.value < physics.table[18]


def test_estimate_returns_the_grade_at_each_threshold():
    scale = load(grade_payload())[0]

    values = [
        estimate_for_primary(scale, primary, scale.max_primary, 10).value
        for primary in (2, 3, 5, 6, 8, 9, 10)
    ]

    assert values == [2, 3, 3, 4, 4, 5, 5]
    assert isinstance(scale, GradeScale)
    assert estimate_for_primary(scale, 0, scale.max_primary, 10).min_pass is None


def test_estimate_clamps_a_primary_score_above_the_sample_maximum():
    scale = load(scale_payload())[0]

    assert estimate_for_primary(scale, 99, 8, 4).scaled_primary == 4


def test_estimate_rejects_an_empty_sample():
    scale = load(scale_payload())[0]

    with pytest.raises(ValueError, match="invalid_score_sample"):
        estimate_for_primary(scale, 0, 0, 4)
