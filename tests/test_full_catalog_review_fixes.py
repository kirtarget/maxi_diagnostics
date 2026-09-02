from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "school" / "diagnostics"
ASSETS = ROOT / "school" / "assets" / "questions"


def _questions() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for path in DIAGNOSTICS.glob("*.json"):
        diagnostic = json.loads(path.read_text(encoding="utf-8"))
        for question in diagnostic["questions"]:
            assert question["id"] not in result
            result[question["id"]] = question
    return result


def _option(question: dict, option_id: str) -> str:
    return next(option["label"] for option in question["options"] if option["id"] == option_id)


def test_reviewed_answer_changes_and_canonical_input_order_are_locked() -> None:
    questions = _questions()

    assert questions["f26-ege-rus-a04"]["correct"] == ["b", "c"]
    assert questions["f26-ege-rus-a04"]["selection_limit"] == 2
    assert questions["q1603"]["correct"] == ["1423"]
    assert questions["q1537"]["correct"] == "o2"

    assert questions["q9886"]["correct"] == ["123"]
    assert questions["q1610"]["correct"] == ["25"]
    assert questions["q3383"]["correct"] == ["34"]


def test_reviewed_blocker_uses_the_verified_full_map() -> None:
    questions = _questions()
    assert questions["q1607"]["asset"] == "assets/questions/q1607.png"

    q1605 = (ASSETS / "q1605.png").read_bytes()
    q1607 = (ASSETS / "q1607.png").read_bytes()
    assert len(q1607) > 100_000
    assert hashlib.sha256(q1607).digest() == hashlib.sha256(q1605).digest()


def test_reviewed_medium_findings_are_unambiguous() -> None:
    questions = _questions()

    assert "уравнением на рисунке" in questions["q9870"]["prompt"]
    assert "Silentium!" in _option(questions["q9878"], "o2")
    assert "Есть в осени первоначальной" not in _option(questions["q9878"], "o2")
    assert "максималь" not in _option(questions["q9858"], "o4").lower()
    assert "превышение стоимости экспорта" in _option(questions["q9883"], "o3")
    assert "листоватого лишайника" in questions["q5882"]["prompt"]
    assert "только прямые пищевые связи" in questions["q5891"]["prompt"]
    assert "не переводя единицы измерения" in questions["q1626"]["prompt"]
    assert "опечатк" not in questions["q1626"]["prompt"].lower()
    assert "ближе к шарниру" in json.dumps(questions["q1646"], ensure_ascii=False)
    assert "одиннадцать рублей" in _option(questions["q3392"], "o4")
    assert "свободу и личную неприкосновенность" in _option(questions["q1547"], "o2")
    assert "религиозными обрядами" in questions["q1551"]["prompt"]


def test_reviewed_editorial_defects_do_not_return() -> None:
    questions = _questions()
    forbidden = {
        "q9877": ("данно м", "стихотворени и"),
        "q9855": ("внутренней энергия тела",),
        "q9896": ("серебря(З)ое",),
        "q9897": ("НЕМАЛЕНЬКЙ",),
        "q5887": ("мышц ы",),
        "q1497": ("последовательнсть",),
        "q1826": ("only watches", "Australi a"),
    }
    for question_id, fragments in forbidden.items():
        payload = json.dumps(questions[question_id], ensure_ascii=False)
        for fragment in fragments:
            assert fragment not in payload

    assert "производитель пищевых продуктов, специализирующийся" in questions["q9881"]["prompt"]
    assert "пользование обществом природными ресурсами" in json.dumps(
        questions["q1528"], ensure_ascii=False
    ).lower()


def test_oge_russian_2026_drafts_are_distinguished_from_legacy_mapping() -> None:
    matrix = (ROOT / "docs" / "FIPI_2026_CONTENT_MATRIX.md").read_text(encoding="utf-8")
    assert "предварительно для `f26-oge-rus-a01`, `f26-oge-rus-a02`" in matrix
    assert "не установлено для legacy" in matrix
    assert "`approval_status` остаётся `draft`" in matrix
