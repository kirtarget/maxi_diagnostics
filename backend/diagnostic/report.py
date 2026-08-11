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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer
from svglib.svglib import svg2rlg

from diagnostic.catalog import DiagnosticCatalog
from diagnostic.school import SchoolConfig, validate_asset_bytes, validate_asset_path


_FONT_ROOT = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_REGULAR = "DiagnosticLiberationSans"
_FONT_BOLD = "DiagnosticLiberationSansBold"
_MAX_QUESTIONS = 200


def _register_fonts() -> None:
    registered = set(pdfmetrics.getRegisteredFontNames())
    if _FONT_REGULAR not in registered:
        pdfmetrics.registerFont(TTFont(_FONT_REGULAR, _FONT_ROOT / "LiberationSans-Regular.ttf"))
    if _FONT_BOLD not in registered:
        pdfmetrics.registerFont(TTFont(_FONT_BOLD, _FONT_ROOT / "LiberationSans-Bold.ttf"))
    pdfmetrics.registerFontFamily(
        "DiagnosticLiberationSans",
        normal=_FONT_REGULAR,
        bold=_FONT_BOLD,
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
    snapshot_school = report_snapshot.get("school") if isinstance(report_snapshot, Mapping) else None
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
    if not isinstance(diagnostic, Mapping):
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

    _register_fonts()
    primary = colors.HexColor(school.brand.colors.primary)
    accent = colors.HexColor(school.brand.colors.accent)
    background = colors.HexColor(school.brand.colors.background)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "DiagnosticTitle", parent=styles["Title"], fontName=_FONT_BOLD,
        fontSize=20, leading=24, textColor=primary, alignment=TA_CENTER, spaceAfter=8 * mm,
    )
    heading = ParagraphStyle(
        "DiagnosticHeading", parent=styles["Heading2"], fontName=_FONT_BOLD,
        fontSize=13, leading=17, textColor=primary, spaceBefore=4 * mm, spaceAfter=2 * mm,
    )
    body = ParagraphStyle(
        "DiagnosticBody", parent=styles["BodyText"], fontName=_FONT_REGULAR,
        fontSize=10, leading=14, textColor=colors.HexColor("#222222"), spaceAfter=2 * mm,
    )
    small = ParagraphStyle(
        "DiagnosticSmall", parent=body, fontSize=8, leading=11, textColor=colors.HexColor("#555555"),
    )

    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"{school.brand.name} - {school.brand.pdf.header}",
        author=school.brand.name,
    )
    story: list[Any] = []
    logo = _optional_image(
        school, school.brand.logo, 34 * mm, 30 * mm, frozen_assets
    )
    if logo is not None:
        logo.hAlign = "CENTER"
        story.extend([logo, Spacer(1, 4 * mm)])
    story.append(Paragraph(_text(school.brand.pdf.header), title))
    story.append(Paragraph(_text(school.brand.name), heading))
    story.append(Paragraph(_text(_value(attempt, "subject", diagnostic.get("subject", ""))), body))
    score = _value(attempt, "score", 0)
    scoring = diagnostic.get("scoring", {})
    default_max_score = scoring.get("max_score", 0) if isinstance(scoring, Mapping) else 0
    max_score = _value(attempt, "max_score", default_max_score)
    correct = _value(attempt, "correct_count", 0)
    story.append(
        Paragraph(
            f"{_text(school.brand.pdf.score_label)}: <b>{_text(score)} / {_text(max_score)}</b>",
            heading,
        )
    )
    story.append(
        Paragraph(
            f"{_text(school.brand.pdf.correct_label)}: {_text(correct)} / {_text(question_count)}",
            body,
        )
    )

    strong_topics = list(_value(attempt, "strong_topics", []) or [])
    growth_topics = list(_value(attempt, "growth_topics", []) or [])
    if strong_topics:
        story.append(Paragraph(_text(school.brand.pdf.strong_topics_label), heading))
        story.append(Paragraph(" + ".join(_text(topic) for topic in strong_topics), body))
    if growth_topics:
        story.append(Paragraph(_text(school.brand.pdf.growth_topics_label), heading))
        story.append(Paragraph(" - ".join(_text(topic) for topic in growth_topics), body))

    result_snapshot = _value(attempt, "result_snapshot", {}) or {}
    forecast = (
        result_snapshot.get("forecast", {})
        if isinstance(result_snapshot, Mapping)
        else {}
    )
    points = forecast.get("points", []) if isinstance(forecast, Mapping) else []
    if isinstance(points, list) and points:
        story.append(Paragraph(_text(school.brand.pdf.forecast_label), heading))
        for point in points[:10]:
            if isinstance(point, Mapping):
                story.append(
                    Paragraph(
                        f"{_text(point.get('label', ''))}: "
                        f"<b>{_text(point.get('value', ''))}</b>",
                        body,
                    )
                )

    answers = _value(attempt, "answers", {}) or {}
    for index, question in enumerate(questions, 1):
        block: list[Any] = [
            Paragraph(f"{index}. {_text(_question_value(question, 'title', ''))}", heading),
            Paragraph(_text(_question_value(question, "prompt", "")), body),
        ]
        image = _optional_image(
            school, _question_value(question, "asset"), 120 * mm, 70 * mm,
            frozen_assets,
        )
        if image is not None:
            block.append(image)
        block.append(
            Paragraph(
                f"{_text(school.brand.pdf.answer_label)}: "
                f"{_text(_answer_text(question, answers.get(_question_value(question, 'id'), '-')))}",
                small,
            )
        )
        story.append(KeepTogether(block))

    if school.links.offers:
        offer = school.links.offers[0]
        story.extend(
            [
                Spacer(1, 6 * mm),
                Paragraph(_text(offer.label), heading),
                Paragraph(_text(offer.url), body),
            ]
        )
    story.extend([Spacer(1, 5 * mm), Paragraph(_text(school.links.website), small)])

    def page(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFillColor(background)
        canvas.rect(0, 0, A4[0], 9 * mm, fill=1, stroke=0)
        canvas.setFillColor(accent)
        canvas.rect(0, A4[1] - 4 * mm, A4[0], 4 * mm, fill=1, stroke=0)
        canvas.setFillColor(primary)
        canvas.setFont(_FONT_REGULAR, 8)
        canvas.drawRightString(A4[0] - 18 * mm, 3.5 * mm, str(doc.page))
        canvas.restoreState()

    document.build(story, onFirstPage=page, onLaterPages=page)
    payload = output.getvalue()
    if len(payload) > 25 * 1024 * 1024:
        raise ValueError("report_too_large")
    return payload
