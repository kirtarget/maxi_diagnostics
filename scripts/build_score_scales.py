"""Build `school/score_scales.json` from the researched 2026 scale tables.

The research file `docs/data/score-scales-2026.json` is keyed by subject slug and
leaves unconfirmed EGE cells as `null`. This script fills those cells by linear
interpolation between their confirmed neighbours, records which primary scores were
filled, and emits one scale per diagnostic actually present in `school/diagnostics`.
Re-running it is idempotent: the output only depends on the two inputs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_PATH = REPOSITORY_ROOT / "docs" / "data" / "score-scales-2026.json"
DIAGNOSTICS_ROOT = REPOSITORY_ROOT / "school" / "diagnostics"
OUTPUT_PATH = REPOSITORY_ROOT / "school" / "score_scales.json"

# The catalog holds one EGE mathematics diagnostic; the research file carries the
# профиль scale under the same slug, which is the scale we publish.
EXAM_KEYS = {"ege": "ЕГЭ", "oge": "ОГЭ"}

# The research file stores titles, dates and notes transliterated into Latin. The
# repository keeps Cyrillic content, so the published wording is restated here from
# `docs/SCORE_SCALES_2026.md` and only the URL is taken from the research file.
SOURCE_TEXT = {
    "ege": (
        "Шкала перевода баллов ЕГЭ 2026 из первичных в тестовые "
        "(агрегатор ctege.info со ссылкой на публикацию Рособрнадзора и ФИПИ)",
        "2026-05-07",
    ),
    "oge": (
        "Рособрнадзор. Рекомендации по переводу суммы первичных баллов ОГЭ 2026 "
        "в пятибалльную систему оценивания (Приложение 1)",
        "2026-02-25",
    ),
}

NOTES = {
    "ege-mathematics": (
        "Профильный уровень. Минимум 27 тестовых баллов действует и для аттестата, "
        "и для вузов."
    ),
    "ege-russian-language": (
        "Минимум для аттестата — 24 тестовых балла, для вузов — 36."
    ),
    "ege-english-language": (
        "Общая шкала для иностранных языков: английского, немецкого, французского "
        "и испанского."
    ),
    "oge-russian-language": (
        "Отметка «4» требует не менее 6 баллов за грамотность (критерии ГК1-ГК4), "
        "отметка «5» — не менее 9 баллов; иначе отметка снижается."
    ),
    "oge-mathematics": (
        "Для любой отметки выше «2» нужно не менее 2 баллов за геометрию "
        "(задания 15-19 и 23-25)."
    ),
    "oge-informatics": "Рекомендуемый порог для профильных классов — 15 баллов.",
    "oge-english-language": (
        "Общая шкала для иностранных языков; суммируются письменная и устная части."
    ),
}


def _round_half_up(value: float) -> int:
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def interpolate(table: list[int | None]) -> tuple[list[int], list[int]]:
    """Fill `null` cells linearly between confirmed neighbours."""
    known = [index for index, value in enumerate(table) if value is not None]
    if not known or known[0] != 0 or known[-1] != len(table) - 1:
        raise ValueError("score_scale_unbounded_gap")
    filled: list[int] = []
    interpolated: list[int] = []
    for index, value in enumerate(table):
        if value is not None:
            filled.append(int(value))
            continue
        left = max(item for item in known if item < index)
        right = min(item for item in known if item > index)
        low = int(table[left])  # type: ignore[arg-type]
        high = int(table[right])  # type: ignore[arg-type]
        filled.append(_round_half_up(low + (high - low) * (index - left) / (right - left)))
        interpolated.append(index)
    if any(filled[index] > filled[index + 1] for index in range(len(filled) - 1)):
        raise ValueError("score_scale_not_monotonic")
    return filled, interpolated


def _confidence(value: str) -> str:
    return "official" if value == "official" else "secondary"


def _source(entry: dict[str, Any], exam_key: str) -> dict[str, str]:
    source = entry.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"score_scale_source_missing:{exam_key}")
    title, date = SOURCE_TEXT[exam_key]
    return {
        "title": title,
        "url": str(source["url"]),
        "date": date,
        "confidence": _confidence(str(entry.get("confidence", ""))),
    }


def catalog_pairs() -> dict[tuple[str, str], tuple[str, str]]:
    """Map (exam_key, subject_slug) -> (exam text, subject text) from the catalog."""
    pairs: dict[tuple[str, str], tuple[str, str]] = {}
    for path in sorted(DIAGNOSTICS_ROOT.glob("*.json")):
        diagnostic = json.loads(path.read_text(encoding="utf-8"))
        exam_key, slug = path.stem.split("-", 1)
        slug = slug.rsplit("-", 1)[0]
        if exam_key not in EXAM_KEYS:
            raise ValueError(f"score_scale_unknown_exam:{path.name}")
        pairs[(exam_key, slug)] = (str(diagnostic["exam"]), str(diagnostic["subject"]))
    return pairs


def build() -> dict[str, Any]:
    research = json.loads(RESEARCH_PATH.read_text(encoding="utf-8"))
    pairs = catalog_pairs()
    scales: list[dict[str, Any]] = []
    for (exam_key, slug), (exam, subject) in sorted(pairs.items()):
        entry = research.get(exam_key, {}).get(slug)
        if entry is None:
            raise ValueError(f"score_scale_missing:{exam_key}-{slug}")
        scale: dict[str, Any] = {
            "id": f"{exam_key}-{slug}",
            "exam": exam,
            "subject": subject,
            "kind": "test_score" if exam_key == "ege" else "grade",
            "max_primary": int(entry["max_primary"]),
        }
        if exam_key == "ege":
            table, interpolated = interpolate(list(entry["table"]))
            scale["min_pass"] = int(entry["min_test_pass"])
            scale["table"] = table
            scale["interpolated_primary"] = interpolated
        else:
            scale["min_pass"] = None
            scale["grades"] = {key: int(value) for key, value in entry["grades"].items()}
            scale["interpolated_primary"] = []
        scale["notes"] = NOTES.get(scale["id"], "")
        scale["source"] = _source(entry, exam_key)
        scales.append(scale)
    return {"scales": scales}


def main() -> int:
    payload = build()
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    interpolated = sum(len(scale["interpolated_primary"]) for scale in payload["scales"])
    print(
        f"OK scales={len(payload['scales'])} interpolated_cells={interpolated} "
        f"path={OUTPUT_PATH.relative_to(REPOSITORY_ROOT).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
