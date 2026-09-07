import os
from uuid import uuid4

import pytest

from diagnostic.admin.repository import list_users
from diagnostic.db import onboarding
from diagnostic.db.core import init_db, close_db, get_pool


pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL required")


@pytest.mark.asyncio
async def test_onboarding_survives_restart_and_schema_reapplication():
    database = os.environ["TEST_DATABASE_URL"]
    user_id = 8_500_000_000 + int(uuid4().hex[:6], 16)
    await init_db(database)
    pool = await get_pool()
    try:
        async with pool.acquire() as connection:
            await connection.execute("INSERT INTO diagnostic_engagements(user_id) VALUES($1)", user_id)
        assert await onboarding.get_status(user_id) == "welcome"
        assert await onboarding.start_selection(user_id) is True
        assert await onboarding.start_selection(user_id) is False
        await close_db()
        await init_db(database)
        assert await onboarding.get_status(user_id) == "selection"
        pool = await get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO diagnostic_progress_profiles(user_id, completion_count) VALUES($1,1)", user_id,
            )
        assert await onboarding.get_status(user_id) == "completed"
        assert await onboarding.start_selection(user_id) is False
        rows = await list_users(user_id=user_id)
        assert len(rows) == 1
        assert rows[0]["completed"] == 1
        assert rows[0]["notifications_enabled"] is True
        assert rows[0]["started"] == 0
    finally:
        pool = await get_pool()
        async with pool.acquire() as connection:
            await connection.execute("DELETE FROM diagnostic_engagements WHERE user_id=$1", user_id)
            await connection.execute("DELETE FROM diagnostic_progress_profiles WHERE user_id=$1", user_id)
        await close_db()
