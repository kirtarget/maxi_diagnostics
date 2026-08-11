"""Premium workbook layout primitives for frozen diagnostic reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    KeepTogether,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from diagnostic.school import SchoolConfig


_FONT_ROOT = Path(__file__).resolve().parent / "assets" / "fonts"
_DISPLAY_FONT = "Forum"
_BODY_FONT = "Manrope"
_BODY_BOLD = "Manrope-Bold"
_LEGACY_REGULAR = "DiagnosticLiberationSans"
_LEGACY_BOLD = "DiagnosticLiberationSansBold"
_TWO_COLUMN_ANSWER_LIMIT = 500


@dataclass(frozen=True)
class ReportTheme:
    primary: colors.Color
    signal: colors.Color
    ink: colors.Color
    paper: colors.Color


def register_report_fonts() -> None:
    registered = set(pdfmetrics.getRegisteredFontNames())
    for name, filename, fallback in (
        (_DISPLAY_FONT, "Forum-Regular.ttf", "LiberationSans-Regular.ttf"),
        (_BODY_FONT, "Manrope-Regular.ttf", "LiberationSans-Regular.ttf"),
        (_BODY_BOLD, "Manrope-Bold.ttf", "LiberationSans-Bold.ttf"),
        (_LEGACY_REGULAR, "LiberationSans-Regular.ttf", None),
        (_LEGACY_BOLD, "LiberationSans-Bold.ttf", None),
    ):
        if name in registered:
            continue
        path = _FONT_ROOT / filename
        if not path.is_file() and fallback is not None:
            path = _FONT_ROOT / fallback
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        _BODY_FONT,
        normal=_BODY_FONT,
        bold=_BODY_BOLD,
    )
    pdfmetrics.registerFontFamily(
        _LEGACY_REGULAR,
        normal=_LEGACY_REGULAR,
        bold=_LEGACY_BOLD,
    )


def make_styles(theme: ReportTheme) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "display": ParagraphStyle(
            "Display",
            parent=base["Title"],
            fontName=_DISPLAY_FONT,
            fontSize=30,
            leading=33,
            textColor=theme.ink,
            spaceAfter=14,
        ),
        "heading": ParagraphStyle(
            "Heading",
            parent=base["Heading2"],
            fontName=_BODY_BOLD,
            fontSize=15,
            leading=19,
            textColor=theme.ink,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=_BODY_FONT,
            fontSize=10,
            leading=15,
            textColor=theme.ink,
            spaceAfter=7,
        ),
        "label": ParagraphStyle(
            "Label",
            parent=base["BodyText"],
            fontName=_BODY_BOLD,
            fontSize=8,
            leading=10,
            textColor=theme.primary,
            spaceAfter=4,
        ),
        "user_answer": ParagraphStyle(
            "UserAnswer",
            parent=base["BodyText"],
            fontName=_BODY_FONT,
            fontSize=9,
            leading=13,
            textColor=theme.ink,
            backColor=theme.paper,
        ),
        "expected_answer": ParagraphStyle(
            "ExpectedAnswer",
            parent=base["BodyText"],
            fontName=_BODY_BOLD,
            fontSize=9,
            leading=13,
            textColor=theme.ink,
            backColor=theme.signal,
        ),
    }


def summary_story(
    attempt: Mapping[str, Any],
    school: SchoolConfig,
    styles: Mapping[str, ParagraphStyle],
) -> list[Any]:
    result = (
        attempt.get("result_snapshot")
        if isinstance(attempt.get("result_snapshot"), Mapping)
        else {}
    )
    score = int(result.get("score") or 0)
    forecast = (
        result.get("forecast")
        if isinstance(result.get("forecast"), Mapping)
        else {}
    )
    points = forecast.get("points") if isinstance(forecast.get("points"), list) else []
    story: list[Any] = [
        Paragraph(escape(school.brand.name), styles["label"]),
        Paragraph("Ваша точка старта", styles["display"]),
        Paragraph(f"Текущий результат: <b>{score}</b>", styles["heading"]),
        Paragraph(
            "Диагностика показывает, что уже получается и где быстрее всего вырастет балл.",
            styles["body"],
        ),
    ]
    persisted_points = [
        point
        for point in points[:2]
        if isinstance(point, Mapping) and point.get("value") is not None
    ]
    if persisted_points:
        rows = [
            [
                Paragraph("Прогноз", styles["label"]),
                Paragraph("Баллы", styles["label"]),
            ]
        ]
        rows.extend(
            [
                Paragraph(escape(str(point.get("label") or "Этап")), styles["body"]),
                Paragraph(escape(str(point["value"])), styles["heading"]),
            ]
            for point in persisted_points
        )
        table = Table(rows, colWidths=[125 * mm, 35 * mm], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#E66A2C")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.extend([Spacer(1, 8 * mm), table])
    return story


def _answer_story(
    user_answer: str,
    expected_answer: str,
    styles: Mapping[str, ParagraphStyle],
) -> list[Any]:
    if max(len(user_answer), len(expected_answer)) > _TWO_COLUMN_ANSWER_LIMIT:
        return [
            Paragraph("Ваш ответ", styles["label"]),
            Paragraph(escape(user_answer), styles["user_answer"]),
            Spacer(1, 3 * mm),
            Paragraph("Правильный ответ", styles["label"]),
            Paragraph(escape(expected_answer), styles["expected_answer"]),
        ]
    answer_table = Table(
        [
            [
                Paragraph("Ваш ответ", styles["label"]),
                Paragraph("Правильный ответ", styles["label"]),
            ],
            [
                Paragraph(escape(user_answer), styles["user_answer"]),
                Paragraph(escape(expected_answer), styles["expected_answer"]),
            ],
        ],
        colWidths=[80 * mm, 80 * mm],
        hAlign="LEFT",
        splitByRow=0,
    )
    answer_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 1), (0, 1), styles["user_answer"].backColor),
                (
                    "BACKGROUND",
                    (1, 1),
                    (1, 1),
                    styles["expected_answer"].backColor,
                ),
                ("BOX", (0, 1), (-1, 1), 0.5, colors.HexColor("#D7D4CB")),
                ("INNERGRID", (0, 1), (-1, 1), 0.5, colors.HexColor("#D7D4CB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 1), (-1, 1), 8),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
                ("LEFTPADDING", (0, 1), (-1, 1), 8),
                ("RIGHTPADDING", (0, 1), (-1, 1), 8),
                ("LEFTPADDING", (0, 0), (-1, 0), 0),
            ]
        )
    )
    return [answer_table]


def review_story(
    review: Mapping[str, Any],
    styles: Mapping[str, ParagraphStyle],
    images: Sequence[Any],
) -> list[Any]:
    number = int(review.get("number") or 0)
    status = "Верно" if review.get("is_correct") else "Нужно разобрать"
    header = KeepTogether(
        [
            Paragraph(f"Задание {number} · {escape(status)}", styles["label"]),
            Paragraph(
                escape(str(review.get("title") or f"Задание {number}")),
                styles["heading"],
            ),
        ]
    )
    user_answer = str(review.get("user_answer") or "Нет ответа")
    expected_answer = str(review.get("expected_answer") or "-")
    story: list[Any] = [
        header,
        Paragraph(escape(str(review.get("prompt") or "")), styles["body"]),
        *images,
        Spacer(1, 3 * mm),
        *_answer_story(user_answer, expected_answer, styles),
        Spacer(1, 5 * mm),
        Paragraph("Как решать", styles["label"]),
        Paragraph(
            escape(
                str(
                    review.get("guidance")
                    or "Сверьте ход решения с правилом по теме задания."
                )
            ),
            styles["body"],
        ),
        Spacer(1, 8 * mm),
    ]
    return story


def route_story(
    attempt: Mapping[str, Any],
    school: SchoolConfig,
    styles: Mapping[str, ParagraphStyle],
) -> list[Any]:
    result = (
        attempt.get("result_snapshot")
        if isinstance(attempt.get("result_snapshot"), Mapping)
        else {}
    )
    raw_topics = result.get("growth_topics") or result.get("weak_topics") or []
    topics = [
        str(item.get("topic") or "") if isinstance(item, Mapping) else str(item)
        for item in raw_topics[:2]
    ]
    route = [f"Закрыть тему «{topic}»" for topic in topics if topic]
    route.append("Проверить рост на следующей диагностике")
    story: list[Any] = [
        Paragraph("Персональный маршрут", styles["display"]),
        Paragraph("Три ближайших действия", styles["label"]),
    ]
    for index, action in enumerate(route[:3], start=1):
        story.append(
            Paragraph(
                f"<b>{index:02d}</b>&nbsp;&nbsp;{escape(str(action))}",
                styles["heading"],
            )
        )
    if school.links.offers:
        story.append(
            Paragraph(
                "Продолжить подготовку можно по ссылке из сообщения бота.",
                styles["body"],
            )
        )
    return story


def draw_page(theme: ReportTheme):
    def _draw(canvas: Canvas, document: BaseDocTemplate) -> None:
        canvas.saveState()
        canvas.setStrokeColor(theme.primary)
        canvas.setLineWidth(1)
        canvas.line(18 * mm, 285 * mm, 192 * mm, 285 * mm)
        canvas.setFillColor(theme.ink)
        canvas.setFont(_BODY_FONT, 8)
        canvas.drawString(18 * mm, 10 * mm, "Персональный отчёт")
        canvas.drawRightString(192 * mm, 10 * mm, str(document.page))
        canvas.restoreState()

    return _draw
