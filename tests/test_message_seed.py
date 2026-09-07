from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from diagnostic.db.messages import PREVIOUS_DEFAULTS, seed_messages
from diagnostic.school import load_school


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_seed_replaces_only_previous_default_text():
    connection = AsyncMock()
    school = load_school(ROOT / "school")

    await seed_messages(connection, school)

    query, rows = connection.executemany.await_args.args
    assert "WHEN message_templates.text=ANY($4::text[]) THEN EXCLUDED.text" in query
    by_key = {row[0]: row for row in rows}
    assert by_key["WELCOME"] == (
        "WELCOME",
        school.brand.messages.welcome,
        "Diagnostic welcome message",
        PREVIOUS_DEFAULTS["WELCOME"],
    )
    assert by_key["GENERIC"][3] == PREVIOUS_DEFAULTS["GENERIC"]
    assert by_key["WELCOME"][1] not in by_key["WELCOME"][3]
    assert "Добро пожаловать в {school_name}." in by_key["WELCOME"][3]
