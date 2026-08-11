import os

import pytest
import pytest_asyncio

from diagnostic.db.core import close_db, init_db
from diagnostic.db.messages import get_message, update_message


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest_asyncio.fixture(autouse=True)
async def database():
    await init_db(os.environ["TEST_DATABASE_URL"])
    yield
    await close_db()


@pytest.mark.asyncio
async def test_seeding_preserves_edited_template_text_and_refreshes_description():
    original = await get_message("WELCOME")
    assert original is not None

    await update_message("WELCOME", "Edited welcome")
    await init_db(os.environ["TEST_DATABASE_URL"])
    seeded_again = await get_message("WELCOME")

    assert seeded_again["text"] == "Edited welcome"
    assert seeded_again["description"] == "Diagnostic welcome message"
