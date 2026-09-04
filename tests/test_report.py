from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Spacer

from diagnostic.catalog import load_catalog
from diagnostic.review import build_review_snapshot
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


def make_review(*, prompt: str, guidance: str) -> dict[str, object]:
    return {
        "question_id": "q1",
        "number": 1,
        "type": "input",
        "topic": "Алгоритмы",
        "title": "Задание 1",
        "prompt": prompt,
        "is_correct": False,
        "user_answer": "12",
        "expected_answer": "16",
        "guidance": guidance,
        "guidance_kind": "fallback",
        "user_value": "12",
        "expected_value": ["16"],
    }


def test_premium_report_never_calls_a_missing_expected_answer_unanswered():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    review = make_review(prompt="Условие", guidance="Разбор")
    review["user_answer"] = "Не отвечено"
    review["expected_answer"] = ""
    attempt = completed_attempt(
        report_snapshot=make_review_report_snapshot(school, diagnostic, [review])
    )

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(build_report(attempt, school))).pages
    )

    assert "Эталонный ответ не сохранён" in text
    assert "\n-\n" not in text


def test_premium_report_does_not_repeat_unanswered_as_the_expected_answer():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    review = make_review(prompt="Условие", guidance="Разбор")
    review["user_answer"] = "Не отвечено"
    review["expected_answer"] = "Не отвечено"
    review.pop("expected_value", None)
    attempt = completed_attempt(
        report_snapshot=make_review_report_snapshot(school, diagnostic, [review])
    )

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(build_report(attempt, school))).pages
    )

    assert "Эталонный ответ не сохранён" in text


def test_premium_report_includes_verified_learning_material_text():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    review = make_review(prompt="Условие", guidance="Разбор")
    review["learning_material_text"] = "Сначала найдите подлежащее и сказуемое в каждой части предложения."
    attempt = completed_attempt(
        report_snapshot=make_review_report_snapshot(school, diagnostic, [review])
    )

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(build_report(attempt, school))).pages
    )

    assert "Как решать" in text
    assert "Сначала найдите подлежащее и сказуемое в каждой части предложения." in text


def make_review_report_snapshot(school, diagnostic, review_snapshot):
    return {
        "diagnostic": {
            "id": diagnostic.id,
            "subject": diagnostic.subject,
            "scoring": diagnostic.scoring.model_dump(mode="json"),
            "questions": [],
        },
        "review_snapshot": review_snapshot,
        "school": {
            "brand": school.brand.model_dump(mode="json"),
            "links": school.links.model_dump(mode="json"),
        },
    }


def test_premium_report_paginates_a_reading_passage_prompt():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    passage = " ".join(
        f"Предложение {index} исходного текста для чтения." for index in range(1, 201)
    )
    assert 6000 < len(passage) <= 10000
    review = make_review(prompt=passage, guidance="Разбор")
    attempt = completed_attempt(
        report_snapshot=make_review_report_snapshot(school, diagnostic, [review])
    )

    pages = PdfReader(BytesIO(build_report(attempt, school))).pages
    text = "\n".join(page.extract_text() or "" for page in pages)

    assert len(pages) > 2
    assert "Предложение 1 исходного" in text
    assert "Предложение 200 исходного" in text
    assert "Как решать" in text


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
    assert "Ваш ответ" in text
    assert "старом формате" in text


def test_premium_report_contains_both_answers_guidance_forecast_and_route():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    review_snapshot = build_review_snapshot(
        diagnostic.questions, completed_attempt()["answers"]
    )
    attempt = completed_attempt(
        report_snapshot=make_review_report_snapshot(
            school, diagnostic, review_snapshot
        ),
        result_snapshot={
            "forecast": {
                "points": [
                    {"id": "stage", "label": "Первый этап", "value": 100}
                ]
            }
        },
    )

    pdf = build_report(attempt, school)
    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages
    )

    assert "Ваша точка старта" in text
    assert "Ваш ответ" in text
    assert "Правильный ответ" in text
    assert "Как решать" in text
    assert "Первый этап" in text
    assert "Персональный маршрут" in text


def test_premium_report_renders_zero_summary_and_frozen_provenance_in_footer():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    snapshot = make_review_report_snapshot(
        school,
        diagnostic,
        [make_review(prompt="Условие", guidance="Решение")],
    )
    snapshot["provenance"] = {
        "attempt_id": "attempt_zero",
        "diagnostic_id": "demo-physics",
        "content_version": "content-v0",
        "exam": "ОГЭ",
        "subject": "Физика",
        "mode": "quick",
    }
    attempt = completed_attempt(
        attempt_id="attempt_zero",
        diagnostic_id="demo-physics",
        content_version="content-v0",
        exam="ОГЭ",
        subject="Физика",
        mode="quick",
        completed_at=datetime(2026, 8, 11, 15, 30, tzinfo=timezone.utc),
        question_count=4,
        correct_count=0,
        score=0,
        max_score=100,
        score_unit="accuracy_percent",
        unassessed_part="Письменная часть не проверялась",
        strong_topics=["Механика"],
        growth_topics=["Оптика"],
        result_snapshot={
            "score": 0,
            "max_score": 100,
            "score_unit": "accuracy_percent",
            "correct_count": 0,
            "question_count": 4,
            "unassessed_part": "Письменная часть не проверялась",
            "strong_topics": [{"topic": "Механика"}],
            "growth_topics": [{"topic": "Оптика"}],
        },
        report_snapshot=snapshot,
    )

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(build_report(attempt, school))).pages
    )

    assert "Предмет: Физика" in text
    assert "Режим: быстрая диагностика" in text
    assert "Дата завершения: 11.08.2026" in text
    assert "Текущий результат: 0 из 100 баллов" in text
    assert "Верных ответов: 0 из 4" in text
    assert "Границы проверки: Письменная часть не проверялась" in text
    assert "Сильные темы: Механика" in text
    assert "Точки роста: Оптика" in text
    assert "ID результата: attempt_zero" in text
    assert "Диагностика: demo-physics" in text
    assert "Версия диагностики: content-v0" in text
    assert "accuracy_percent" not in text


def test_premium_report_footer_fits_maximum_persisted_provenance():
    from diagnostic.report import build_report
    from diagnostic.report_layout import (
        _BODY_FONT,
        _provenance_lines,
        register_report_fonts,
    )
    from reportlab.pdfbase import pdfmetrics

    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    diagnostic_id = "d" * 64
    content_version = "f" * 64
    snapshot = make_review_report_snapshot(
        school,
        diagnostic,
        [make_review(prompt="Условие", guidance="Решение")],
    )
    snapshot["provenance"] = {
        "attempt_id": "attempt_maximum_provenance",
        "diagnostic_id": diagnostic_id,
        "content_version": content_version,
        "exam": "ЕГЭ",
        "subject": "Математика",
        "mode": "full",
    }
    attempt = completed_attempt(
        attempt_id="attempt_maximum_provenance",
        diagnostic_id=diagnostic_id,
        content_version=content_version,
        report_snapshot=snapshot,
    )

    register_report_fonts()
    footer_lines = _provenance_lines(attempt)
    available_width = 174 * mm

    assert all(
        pdfmetrics.stringWidth(line, _BODY_FONT, 6.5) <= available_width
        for line in footer_lines
    )

    text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(BytesIO(build_report(attempt, school))).pages
    )
    assert diagnostic_id in text
    assert content_version in text


def test_premium_report_uses_legacy_snapshot_fallbacks_without_current_catalog():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    snapshot = make_review_report_snapshot(
        school,
        diagnostic,
        [make_review(prompt="Условие", guidance="Решение")],
    )
    snapshot["diagnostic"]["subject"] = "Сохранённый предмет"
    attempt = completed_attempt(
        subject="",
        content_version="",
        completed_at=None,
        report_snapshot=snapshot,
    )

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(build_report(attempt, school))).pages
    )

    assert "Предмет: Сохранённый предмет" in text
    assert "Дата завершения: не сохранена" in text
    assert "Версия диагностики: не сохранена" in text


def test_report_theme_maps_distinct_semantic_school_colors():
    from diagnostic.report import _report_theme

    school = load_school(SAMPLE_SCHOOL)
    school.brand.colors.primary = "#112233"
    school.brand.colors.accent = "#DDEEFF"
    school.brand.colors.background = "#010203"
    school.brand.colors.signal = "#445566"
    school.brand.colors.ink = "#778899"
    school.brand.colors.paper = "#AABBCC"

    theme = _report_theme(school)

    assert theme.primary == colors.HexColor("#112233")
    assert theme.signal == colors.HexColor("#445566")
    assert theme.ink == colors.HexColor("#778899")
    assert theme.paper == colors.HexColor("#AABBCC")


def test_long_review_can_split_across_pages_without_blank_page():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    review = make_review(
        prompt="Длинное условие. " * 160,
        guidance="Шаг решения. " * 100,
    )
    snapshot = make_review_report_snapshot(school, diagnostic, [review])

    pdf = build_report(
        completed_attempt(
            question_count=1,
            report_snapshot=snapshot,
            result_snapshot={"score": 0, "growth_topics": ["Алгоритмы"]},
        ),
        school,
    )
    pages = PdfReader(BytesIO(pdf)).pages

    assert 2 <= len(pages) <= 6
    assert all((page.extract_text() or "").strip() for page in pages)


def test_answer_labels_do_not_split_from_answer_values():
    from diagnostic.report_layout import (
        ReportTheme,
        _answer_story,
        make_styles,
        register_report_fonts,
    )

    register_report_fonts()
    styles = make_styles(
        ReportTheme(
            primary=colors.HexColor("#5636D3"),
            signal=colors.HexColor("#C7F36B"),
            ink=colors.HexColor("#222222"),
            paper=colors.HexColor("#F7F5EF"),
        )
    )
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    document.build([Spacer(1, 250 * mm), *_answer_story("12", "16", styles)])
    pages = [
        page.extract_text() or ""
        for page in PdfReader(BytesIO(output.getvalue())).pages
    ]
    label_page = next(page for page in pages if "Правильный ответ" in page)

    assert "12" in label_page
    assert "16" in label_page


def test_long_answer_label_stays_with_first_splittable_fragment():
    from diagnostic.report_layout import (
        ReportTheme,
        _answer_story,
        make_styles,
        register_report_fonts,
    )

    register_report_fonts()
    styles = make_styles(
        ReportTheme(
            primary=colors.HexColor("#5636D3"),
            signal=colors.HexColor("#C7F36B"),
            ink=colors.HexColor("#222222"),
            paper=colors.HexColor("#F7F5EF"),
        )
    )
    long_answer = "НАЧАЛО ДЛИННОГО ОТВЕТА " + "фрагмент " * 1000
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    document.build(
        [Spacer(1, 250 * mm), *_answer_story(long_answer, "16", styles)]
    )
    pages = [
        page.extract_text() or ""
        for page in PdfReader(BytesIO(output.getvalue())).pages
    ]
    label_page = next(page for page in pages if "Ваш ответ" in page)

    assert "НАЧАЛО ДЛИННОГО ОТВЕТА" in label_page
    assert sum("фрагмент" in page for page in pages) >= 2


def test_premium_report_rejects_missing_frozen_school():
    from diagnostic.report import build_report

    school = load_school(SAMPLE_SCHOOL)
    school.brand.name = "ЖИВАЯ ШКОЛА"
    diagnostic = load_catalog(load_school(SAMPLE_SCHOOL)).get("demo-math")
    snapshot = make_review_report_snapshot(
        school,
        diagnostic,
        [make_review(prompt="Условие", guidance="Решение")],
    )
    del snapshot["school"]

    with pytest.raises(ValueError, match="report_snapshot_invalid"):
        build_report(
            completed_attempt(question_count=1, report_snapshot=snapshot),
            school,
        )


def test_build_report_renders_every_image_from_completion_snapshot(monkeypatch):
    from diagnostic import report

    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    questions = [
        question.model_dump(mode="json", exclude={"correct"})
        for question in diagnostic.questions
    ]
    questions[0]["asset"] = None
    questions[0]["assets"] = [
        "assets/question-1.svg",
        "assets/question-2.svg",
    ]
    report_snapshot = {
        "diagnostic": {
            "id": diagnostic.id,
            "subject": diagnostic.subject,
            "scoring": diagnostic.scoring.model_dump(mode="json"),
            "questions": questions,
        },
        "mode": "full",
    }
    rendered: list[str | None] = []

    def record_image(_school, relative_path, *_args):
        rendered.append(relative_path)
        return None

    monkeypatch.setattr(report, "_optional_image", record_image)

    report.build_report(completed_attempt(report_snapshot=report_snapshot), school)

    assert rendered[1:3] == [
        "assets/question-1.svg",
        "assets/question-2.svg",
    ]


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
