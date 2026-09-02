"""Branded, bounded PDF reports built from persisted diagnostic results."""

from __future__ import annotations

import json
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
from zipfile import BadZipFile, ZipFile

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer
from svglib.svglib import svg2rlg

from diagnostic.catalog import DiagnosticCatalog
from diagnostic.report_layout import (
    ReportTheme,
    draw_page,
    make_styles,
    register_report_fonts,
    review_story,
    route_story,
    summary_story,
)
from diagnostic.school import SchoolConfig, validate_asset_bytes, validate_asset_path
from diagnostic.score_text import estimate_caption, estimate_headline


_FONT_REGULAR = "DiagnosticLiberationSans"
_FONT_BOLD = "DiagnosticLiberationSansBold"
_MAX_QUESTIONS = 200


def _register_fonts() -> None:
    register_report_fonts()


def _report_theme(school: SchoolConfig) -> ReportTheme:
    return ReportTheme(
        primary=colors.HexColor(school.brand.colors.primary),
        signal=colors.HexColor(school.brand.colors.signal),
        ink=colors.HexColor(school.brand.colors.ink),
        paper=colors.HexColor(school.brand.colors.paper),
        accent=colors.HexColor(school.brand.colors.accent),
        background=colors.HexColor(school.brand.colors.background),
    )


def _value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, TypeError):
        value = default
    return default if value is None else value


def _text(value: object) -> str:
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return escape(str(value), {'"': "&quot;", "'": "&#39;"})


def _optional_image(
    school: SchoolConfig,
    relative_path: str | None,
    max_width: float,
    max_height: float,
    frozen_assets: Mapping[str, bytes] | None = None,
):
    if not relative_path:
        return None
    try:
        suffix = Path(relative_path).suffix.lower()
        if suffix not in {".svg", ".png", ".jpg", ".jpeg"}:
            return None
        if frozen_assets is not None:
            raw = frozen_assets.get(relative_path)
            if raw is None:
                return None
        else:
            path = school.resolve_asset(relative_path)
            if not path.is_file():
                return None
            raw = path.read_bytes()
        validate_asset_bytes(relative_path, raw)
        if suffix == ".svg":
            image = svg2rlg(BytesIO(raw))
            if image is None or image.width <= 0 or image.height <= 0:
                return None
            scale = min(max_width / image.width, max_height / image.height)
            image.scale(scale, scale)
            image.width *= scale
            image.height *= scale
            return image
        source = BytesIO(raw)
        width, height = ImageReader(source).getSize()
        if width <= 0 or height <= 0 or width * height > 16_000_000:
            return None
        source.seek(0)
        image = Image(source)
        image._restrictSize(max_width, max_height)
        return image
    except Exception:
        return None


def _frozen_assets(payload: bytes | None) -> dict[str, bytes] | None:
    if not payload:
        return None
    if len(payload) > 25 * 1024 * 1024:
        raise ValueError("report_assets_invalid")
    assets: dict[str, bytes] = {}
    total = 0
    try:
        with ZipFile(BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) > 201:
                raise ValueError("report_assets_invalid")
            for info in infos:
                validate_asset_path(info.filename)
                if info.is_dir() or info.file_size > 5 * 1024 * 1024:
                    raise ValueError("report_assets_invalid")
                data = archive.read(info)
                total += len(data)
                if total > 20 * 1024 * 1024 or info.filename in assets:
                    raise ValueError("report_assets_invalid")
                assets[info.filename] = data
    except (BadZipFile, KeyError, OSError, ValueError):
        raise ValueError("report_assets_invalid") from None
    return assets


def _question_value(question: Mapping[str, Any] | object, key: str, default: Any = None) -> Any:
    if isinstance(question, Mapping):
        return question.get(key, default)
    return getattr(question, key, default)


def _question_asset_paths(question: Mapping[str, Any] | object) -> tuple[str, ...]:
    assets = _question_value(question, "assets")
    if isinstance(assets, (list, tuple)):
        return tuple(asset for asset in assets if isinstance(asset, str))
    asset = _question_value(question, "asset")
    return (asset,) if isinstance(asset, str) and asset else ()


def _review_asset_paths(review: Mapping[str, Any]) -> tuple[str, ...]:
    assets = review.get("assets")
    if isinstance(assets, (list, tuple)):
        return tuple(asset for asset in assets if isinstance(asset, str))
    asset = review.get("asset")
    return (asset,) if isinstance(asset, str) and asset else ()


def _answer_text(question: Mapping[str, Any] | object, answer: object) -> str:
    options = {
        str(_question_value(option, "id", "")): str(_question_value(option, "label", ""))
        for option in (_question_value(question, "options", []) or [])
    }
    if isinstance(answer, str):
        return options.get(answer, answer)
    if isinstance(answer, list):
        return ", ".join(options.get(str(value), str(value)) for value in answer)
    if isinstance(answer, Mapping):
        items = {
            str(_question_value(item, "id", "")): str(_question_value(item, "label", ""))
            for item in (_question_value(question, "items", []) or [])
        }
        return "; ".join(
            f"{items.get(str(item_id), str(item_id))}: {options.get(str(value), str(value))}"
            for item_id, value in answer.items()
        )
    return str(answer)


def _legacy_styles(school: SchoolConfig) -> dict[str, ParagraphStyle]:
    primary = colors.HexColor(school.brand.colors.primary)
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "DiagnosticBody",
        parent=base["BodyText"],
        fontName=_FONT_REGULAR,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#222222"),
        spaceAfter=2 * mm,
    )
    return {
        "title": ParagraphStyle(
            "DiagnosticTitle",
            parent=base["Title"],
            fontName=_FONT_BOLD,
            fontSize=20,
            leading=24,
            textColor=primary,
            alignment=TA_CENTER,
            spaceAfter=8 * mm,
        ),
        "heading": ParagraphStyle(
            "DiagnosticHeading",
            parent=base["Heading2"],
            fontName=_FONT_BOLD,
            fontSize=13,
            leading=17,
            textColor=primary,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "body": body,
        "small": ParagraphStyle(
            "DiagnosticSmall",
            parent=body,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#555555"),
        ),
    }


def _legacy_story(
    attempt: Mapping[str, Any],
    school: SchoolConfig,
    diagnostic: Mapping[str, Any],
    questions: list[Any] | tuple[Any, ...],
    frozen_assets: Mapping[str, bytes] | None,
    styles: Mapping[str, ParagraphStyle],
) -> list[Any]:
    story: list[Any] = []
    logo = _optional_image(school, school.brand.logo, 34 * mm, 30 * mm, frozen_assets)
    if logo is not None:
        logo.hAlign = "CENTER"
        story.extend([logo, Spacer(1, 4 * mm)])
    story.extend(
        [
            Paragraph(_text(school.brand.pdf.header), styles["title"]),
            Paragraph(_text(school.brand.name), styles["heading"]),
            Paragraph(
                _text(_value(attempt, "subject", diagnostic.get("subject", ""))),
                styles["body"],
            ),
            Paragraph(
                "Этот отчёт создан в старом формате: для этой попытки не был сохранён "
                "подробный разбор с правильными ответами и рекомендациями.",
                styles["small"],
            ),
        ]
    )
    score = _value(attempt, "score", 0)
    scoring = diagnostic.get("scoring", {})
    default_max_score = scoring.get("max_score", 0) if isinstance(scoring, Mapping) else 0
    max_score = _value(attempt, "max_score", default_max_score)
    correct = _value(attempt, "correct_count", 0)
    result_snapshot = _value(attempt, "result_snapshot", {}) or {}
    estimate = (
        result_snapshot.get("estimate") if isinstance(result_snapshot, Mapping) else None
    )
    headline = estimate_headline(estimate, _value(attempt, "exam", ""))
    caption = estimate_caption(estimate)
    if headline is not None and caption is not None:
        story.extend(
            [
                Paragraph(f"<b>{_text(headline)}</b>", styles["heading"]),
                Paragraph(_text(caption), styles["small"]),
            ]
        )
    story.extend(
        [
            Paragraph(
                f"{_text(school.brand.pdf.score_label)}: "
                f"<b>{_text(score)} / {_text(max_score)}</b>",
                styles["heading"],
            ),
            Paragraph(
                f"{_text(school.brand.pdf.correct_label)}: "
                f"{_text(correct)} / {_text(_value(attempt, 'question_count', 0))}",
                styles["body"],
            ),
        ]
    )

    strong_topics = list(_value(attempt, "strong_topics", []) or [])
    growth_topics = list(_value(attempt, "growth_topics", []) or [])
    if strong_topics:
        story.append(
            Paragraph(_text(school.brand.pdf.strong_topics_label), styles["heading"])
        )
        story.append(
            Paragraph(" + ".join(_text(topic) for topic in strong_topics), styles["body"])
        )
    if growth_topics:
        story.append(
            Paragraph(_text(school.brand.pdf.growth_topics_label), styles["heading"])
        )
        story.append(
            Paragraph(" - ".join(_text(topic) for topic in growth_topics), styles["body"])
        )

    forecast = (
        result_snapshot.get("forecast", {})
        if isinstance(result_snapshot, Mapping)
        else {}
    )
    points = forecast.get("points", []) if isinstance(forecast, Mapping) else []
    if isinstance(points, list) and points:
        story.append(Paragraph(_text(school.brand.pdf.forecast_label), styles["heading"]))
        for point in points[:10]:
            if isinstance(point, Mapping):
                story.append(
                    Paragraph(
                        f"{_text(point.get('label', ''))}: "
                        f"<b>{_text(point.get('value', ''))}</b>",
                        styles["body"],
                    )
                )

    answers = _value(attempt, "answers", {}) or {}
    for index, question in enumerate(questions, 1):
        story.extend(
            [
                Paragraph(
                    f"{index}. {_text(_question_value(question, 'title', ''))}",
                    styles["heading"],
                ),
                Paragraph(_text(_question_value(question, "prompt", "")), styles["body"]),
            ]
        )
        for asset in _question_asset_paths(question):
            image = _optional_image(
                school, asset, 120 * mm, 70 * mm, frozen_assets,
            )
            if image is not None:
                story.append(image)
        story.append(
            Paragraph(
                f"{_text(school.brand.pdf.answer_label)}: "
                f"{_text(_answer_text(question, answers.get(_question_value(question, 'id'), '-')))}",
                styles["small"],
            )
        )

    if school.links.offers:
        offer = school.links.offers[0]
        story.extend(
            [
                Spacer(1, 6 * mm),
                Paragraph(_text(offer.label), styles["heading"]),
                Paragraph(_text(offer.url), styles["body"]),
            ]
        )
    story.extend(
        [Spacer(1, 5 * mm), Paragraph(_text(school.links.website), styles["small"])]
    )
    return story


def build_report(
    attempt: Mapping[str, Any], school: SchoolConfig, catalog: DiagnosticCatalog | None = None
) -> bytes:
    """Create a school-branded PDF only for a persisted completed attempt."""
    if _value(attempt, "status") != "completed":
        raise ValueError("completed_attempt_required")
    question_count = int(_value(attempt, "question_count", 0))
    if question_count < 1 or question_count > _MAX_QUESTIONS:
        raise ValueError("report_question_limit")

    report_snapshot = _value(attempt, "report_snapshot", {}) or {}
    review_snapshot = (
        report_snapshot.get("review_snapshot")
        if isinstance(report_snapshot, Mapping)
        else None
    )
    snapshot_school = report_snapshot.get("school") if isinstance(report_snapshot, Mapping) else None
    if isinstance(review_snapshot, list) and not isinstance(snapshot_school, Mapping):
        raise ValueError("report_snapshot_invalid")
    if isinstance(snapshot_school, Mapping):
        try:
            school = SchoolConfig(
                root=school.root,
                brand=snapshot_school["brand"],
                links=snapshot_school["links"],
            )
        except Exception:
            raise ValueError("report_snapshot_invalid") from None
    frozen_assets = _frozen_assets(_value(attempt, "report_assets"))
    diagnostic = report_snapshot.get("diagnostic") if isinstance(report_snapshot, Mapping) else None
    has_completion_snapshot = isinstance(diagnostic, Mapping) or isinstance(review_snapshot, list)
    if not isinstance(diagnostic, Mapping):
        if isinstance(review_snapshot, list):
            diagnostic = {
                "id": str(_value(attempt, "diagnostic_id", "")),
                "subject": str(_value(attempt, "subject", "")),
                "scoring": {},
                "questions": [],
            }
            questions = []
        else:
            if catalog is None:
                raise ValueError("report_snapshot_required")
            current = catalog.get(str(_value(attempt, "diagnostic_id")))
            mode = str(_value(attempt, "mode", "full"))
            questions = catalog.questions_for_mode(current.id, mode)  # type: ignore[arg-type]
            diagnostic = {
                "id": current.id,
                "subject": current.subject,
                "scoring": current.scoring.model_dump(mode="json"),
                "questions": questions,
            }
    else:
        questions = diagnostic.get("questions", [])
    if not isinstance(questions, (list, tuple)):
        raise ValueError("report_snapshot_invalid")
    if len(questions) > _MAX_QUESTIONS:
        raise ValueError("report_question_limit")
    if isinstance(review_snapshot, list):
        if not review_snapshot or len(review_snapshot) > _MAX_QUESTIONS:
            raise ValueError("report_question_limit")
        if any(not isinstance(review, Mapping) for review in review_snapshot):
            raise ValueError("report_snapshot_invalid")

    _register_fonts()
    theme = _report_theme(school)

    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"{school.brand.name} - {school.brand.pdf.header}",
        author=school.brand.name,
    )
    if isinstance(review_snapshot, list):
        premium_styles = make_styles(theme)
        story = summary_story(attempt, school, premium_styles)
        story.append(PageBreak())
        snapshot_assets = frozen_assets if frozen_assets is not None else {}
        for review in review_snapshot:
            images = []
            for asset in _review_asset_paths(review):
                image = _optional_image(
                    school, asset, 160 * mm, 85 * mm, snapshot_assets,
                )
                if image is not None:
                    image.hAlign = "LEFT"
                    images.append(image)
            story.extend(review_story(review, premium_styles, images))
        story.append(PageBreak())
        story.extend(route_story(attempt, school, premium_styles))
        page = draw_page(theme, attempt)
    else:
        legacy_assets = (
            frozen_assets if frozen_assets is not None else {}
        ) if has_completion_snapshot else frozen_assets
        legacy_styles = _legacy_styles(school)
        story = _legacy_story(
            attempt,
            school,
            diagnostic,
            questions,
            legacy_assets,
            legacy_styles,
        )

        def page(canvas, doc) -> None:
            canvas.saveState()
            canvas.setFillColor(theme.background)
            canvas.rect(0, 0, A4[0], 9 * mm, fill=1, stroke=0)
            canvas.setFillColor(theme.primary)
            canvas.rect(0, A4[1] - 4 * mm, A4[0], 4 * mm, fill=1, stroke=0)
            canvas.setFillColor(theme.primary)
            canvas.setFont(_FONT_REGULAR, 8)
            canvas.drawRightString(A4[0] - 18 * mm, 3.5 * mm, str(doc.page))
            canvas.restoreState()

    document.build(story, onFirstPage=page, onLaterPages=page)
    payload = output.getvalue()
    if len(payload) > 25 * 1024 * 1024:
        raise ValueError("report_too_large")
    return payload
