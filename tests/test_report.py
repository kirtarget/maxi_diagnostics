from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pypdf import PdfReader

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHOOL = ROOT / "tests/fixtures/sample-school"


def completed_attempt(**overrides):
    attempt = {
        "attempt_id": "attempt_123",
        "user_id": 42,
        "diagnostic_id": "demo-math",
        "exam": "demo",
        "subject": "Математика",
        "mode": "full",
        "status": "completed",
        "question_count": 4,
        "answers": {"q1": "2", "q2": ["1", "3"], "q3": {"a": "2", "b": "1"}, "q4": "42"},
        "correct_count": 4,
        "score": 100,
        "max_score": 100,
        "score_unit": "accuracy_percent",
        "strong_topics": ["Вычисления", "Дроби"],
        "growth_topics": ["Уравнения"],
        "result_snapshot": {"score": 100, "correct_count": 4},
    }
    attempt.update(overrides)
    return attempt


def test_build_report_embeds_cyrillic_brand_catalog_and_persisted_result():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    pdf = build_report(completed_attempt(), school, load_catalog(school))
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)

    assert pdf.startswith(b"%PDF")
    assert "ДИАГНОСТИКА ЗНАНИЙ" in text
    assert school.brand.name in text
    assert "Математика" in text
    assert "100" in text
    assert "Результат" in text
    assert "Правильных ответов" in text
    assert "Сильные темы" in text
    assert "Точки роста" in text
    assert "Ваш ответ" in text
    assert "Уравнения" in text


def test_build_report_escapes_reportlab_markup_and_tolerates_bad_optional_assets():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    school.brand.logo = "assets/missing.png"
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    pdf = build_report(
        completed_attempt(subject='<b color="red">Алгебра</b>', answers={"q1": "<b>опасно</b>"}),
        school,
        catalog,
    )
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)

    assert '<b color="red">Алгебра</b>' in text
    assert "<b>опасно</b>" in text


def test_build_report_rejects_noncompleted_and_more_than_200_questions():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    catalog = load_catalog(school)
    with pytest.raises(ValueError, match="completed_attempt_required"):
        build_report(completed_attempt(status="in_progress"), school, catalog)
    with pytest.raises(ValueError, match="report_question_limit"):
        build_report(completed_attempt(question_count=201), school, catalog)


def test_build_report_supports_the_200_question_boundary():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    catalog = load_catalog(school)
    diagnostic = catalog.get("demo-math")
    questions = tuple(
        diagnostic.questions[0].model_copy(update={"id": f"q{index}", "title": f"Задание {index}"})
        for index in range(1, 201)
    )
    bounded_catalog = catalog.model_copy(
        update={"diagnostics": (diagnostic.model_copy(update={"questions": questions}),)}
    )
    pdf = build_report(
        completed_attempt(question_count=200, answers={f"q{index}": "2" for index in range(1, 201)}),
        school,
        bounded_catalog,
    )

    assert len(PdfReader(BytesIO(pdf)).pages) > 1


def test_build_report_uses_private_completion_snapshot_without_current_catalog():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    catalog = load_catalog(school)
    diagnostic = catalog.get("demo-math")
    report_snapshot = {
        "diagnostic": {
            "id": diagnostic.id,
            "subject": diagnostic.subject,
            "scoring": diagnostic.scoring.model_dump(mode="json"),
            "questions": [
                question.model_dump(mode="json", exclude={"correct"})
                for question in diagnostic.questions
            ],
        },
        "mode": "full",
    }

    pdf = build_report(completed_attempt(report_snapshot=report_snapshot), school)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)

    assert diagnostic.questions[0].prompt in text
    assert "correct" not in str(report_snapshot)
    assert "2" in text


def test_build_report_uses_frozen_safe_internal_svg_without_live_assets(tmp_path: Path):
    from diagnostic.report import _optional_image

    school = load_school(SAMPLE_SCHOOL).model_copy(update={"root": tmp_path})
    raw = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
        b'<defs><circle id="dot" cx="5" cy="5" r="4"/></defs>'
        b'<use href="#dot"/></svg>'
    )

    image = _optional_image(
        school, "assets/logo.svg", 100, 100, {"assets/logo.svg": raw}
    )

    assert image is not None
    assert image.width == pytest.approx(100)
    assert image.height == pytest.approx(50)


def test_build_report_rejects_a_document_above_the_delivery_limit(monkeypatch):
    from diagnostic import report

    class OversizedDocument:
        def __init__(self, output, **_):
            self.output = output

        def build(self, *_args, **_kwargs):
            self.output.write(b"x" * (25 * 1024 * 1024 + 1))

    school = load_school(SAMPLE_SCHOOL)
    monkeypatch.setattr(report, "SimpleDocTemplate", OversizedDocument)

    with pytest.raises(ValueError, match="report_too_large"):
        report.build_report(completed_attempt(), school, load_catalog(school))
