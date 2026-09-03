"""Guard the single "ты" voice: no formal-address markers may regress in.

The owner decided the bot speaks to students the same way the Mini App does —
informal "ты", warm, short, no officialese. This test scans every place a
default student-facing string lives (school brand configs, the pristine
templates ``scripts/init_school.py`` accepts, and the source of the bot
handlers/follow-ups that build text at runtime) for the formal-address
markers defined in ``diagnostic.message_validation``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from diagnostic.message_validation import find_formal_address


ROOT = Path(__file__).resolve().parents[1]

# Interface labels that are full sentences spoken to the student (as opposed
# to short button captions like "Мои результаты", which are not address
# forms at all and are shared verbatim with the PDF/admin surfaces).
_SENTENCE_INTERFACE_KEYS = (
    "plan_for", "keep_strong", "focus_next", "open_result_hint",
)

_BRAND_FILES = (
    ROOT / "school/brand.json",
    ROOT / "tests/fixtures/pristine_brand.json",
    ROOT / "tests/fixtures/sample-school/brand.json",
)

# Source files that build student-facing bot text; only their Cyrillic
# string literals matter here, but scanning the whole file is simpler and
# just as safe since non-literal source never contains Cyrillic words.
_BOT_SOURCE_FILES = (
    ROOT / "backend/diagnostic/bot/handlers.py",
    ROOT / "backend/diagnostic/bot/keyboards.py",
    ROOT / "backend/diagnostic/followups.py",
    ROOT / "backend/diagnostic/score_text.py",
)

_CYRILLIC_STRING_LITERAL = re.compile(r'(["\'])((?:(?!\1).)*[а-яА-ЯёЁ](?:(?!\1).)*)\1')


def _brand_strings(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    strings = dict(data.get("messages", {}))
    interface = data.get("interface", {})
    for key in _SENTENCE_INTERFACE_KEYS:
        if key in interface:
            strings[f"interface.{key}"] = interface[key]
    return strings


def test_default_brand_messages_use_informal_address():
    for path in _BRAND_FILES:
        for key, text in _brand_strings(path).items():
            assert not find_formal_address(text), (
                f"{path}: {key!r} contains formal address: {text!r}"
            )


def test_bot_source_literals_use_informal_address():
    for path in _BOT_SOURCE_FILES:
        source = path.read_text(encoding="utf-8")
        for _quote, literal in _CYRILLIC_STRING_LITERAL.findall(source):
            assert not find_formal_address(literal), (
                f"{path}: string literal contains formal address: {literal!r}"
            )
