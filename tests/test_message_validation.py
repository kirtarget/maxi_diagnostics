from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from diagnostic.message_validation import validate_message_template
from diagnostic.school import load_school


ROOT = Path(__file__).resolve().parents[1]
VALUES = {
    "school_name": "Школа",
    "school_short_name": "Школа",
    "primary_offer_label": "Подготовка",
    "primary_offer_url": "https://example.com/offer",
    "website_url": "https://example.com",
    "support_url": "https://example.com/support",
    "privacy_url": "https://example.com/privacy",
    "subject": "Математика",
    "mode": "full",
}


@pytest.mark.parametrize("line_break", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_message_template_accepts_paragraph_line_breaks(line_break: str):
    template = line_break.join(("<b>Результат готов</b>", "", "Открой подробный разбор."))

    assert validate_message_template("RESULT_UNVIEWED", template, VALUES) == template


@pytest.mark.parametrize(
    "character",
    [
        pytest.param("\r", id="bare-carriage-return"),
        pytest.param("\t", id="tab"),
        pytest.param("\0", id="null"),
        pytest.param("\u200b", id="zero-width-space"),
        pytest.param("\u2028", id="line-separator"),
        pytest.param("\u2029", id="paragraph-separator"),
    ],
)
def test_message_template_rejects_non_line_break_control_characters(character: str):
    with pytest.raises(ValueError, match="message_text_invalid"):
        validate_message_template(
            "WELCOME",
            f"<b>Привет</b>{character}Открой диагностику.",
            VALUES,
        )


@pytest.mark.parametrize("line_break", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_school_config_accepts_multiline_message_template(
    tmp_path: Path, line_break: str
):
    school_root = tmp_path / "school"
    shutil.copytree(ROOT / "tests/fixtures/sample-school", school_root)
    brand_path = school_root / "brand.json"
    brand = json.loads(brand_path.read_text(encoding="utf-8"))
    brand["messages"]["welcome"] = line_break.join(
        (
            "<b>Привет</b>",
            "",
            "Здесь можно проверить текущий уровень.",
            "",
            "Выбери предмет и начни диагностику.",
        )
    )
    brand_path.write_text(json.dumps(brand, ensure_ascii=False), encoding="utf-8")

    school = load_school(school_root)

    assert school.brand.messages.welcome == brand["messages"]["welcome"]
