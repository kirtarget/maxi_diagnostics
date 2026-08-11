"""Validation for text rendered with the bundled PDF fonts."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from reportlab.pdfbase.ttfonts import TTFont


FONT_ROOT = Path(__file__).resolve().parent / "assets" / "fonts"
FONT_REGULAR_PATH = FONT_ROOT / "LiberationSans-Regular.ttf"
FONT_BOLD_PATH = FONT_ROOT / "LiberationSans-Bold.ttf"


@lru_cache(maxsize=1)
def _supported_codepoints() -> frozenset[int]:
    regular = set(TTFont("DiagnosticCoverageRegular", FONT_REGULAR_PATH).face.charToGlyph)
    bold = set(TTFont("DiagnosticCoverageBold", FONT_BOLD_PATH).face.charToGlyph)
    return frozenset(regular & bold)


def validate_report_text(value: str) -> str:
    """Reject text the bundled regular and bold PDF fonts cannot render."""
    supported = _supported_codepoints()
    if any(ord(character) not in supported for character in value):
        raise ValueError("unsupported_report_character")
    return value
