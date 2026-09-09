"""Editable diagnostic message templates."""

from __future__ import annotations

from typing import Final

from diagnostic.db.core import get_pool
from diagnostic.school import SchoolConfig

MESSAGE_DESCRIPTIONS: Final[dict[str, str]] = {
    "WELCOME": "Diagnostic welcome message",
    "RESULTS_EMPTY": "Empty results message",
    "PLAN_EMPTY": "Empty plan message",
    "DATA_ERASED": "Temporary response after diagnostic data erasure",
    "QUICK_COMPLETE": "Quick completion message",
    "FULL_COMPLETE": "Full completion message",
    "NOT_STARTED": "Not-started reminder",
    "INCOMPLETE": "Incomplete reminder",
    "RESULT_UNVIEWED": "Unviewed result reminder",
    "DAY_FOLLOWUP": "Day follow-up",
    "QUICK_TO_FULL": "Quick-to-full follow-up",
    "MONTH_RETEST": "Monthly retest",
    "LIVES_REFILL": "Trainer lives refilled reminder",
    "STREAK_SAVE": "Evening nudge to save an idle streak",
}
MESSAGE_KEYS: Final[frozenset[str]] = frozenset(MESSAGE_DESCRIPTIONS)
PREVIOUS_DEFAULTS: Final[dict[str, str]] = {
    "WELCOME": "Привет! Это {school_name} — начнём готовиться?",
    "RESULTS_EMPTY": "У тебя пока нет завершённых диагностик.",
    "PLAN_EMPTY": "Твой учебный план появится после диагностики.",
    "DATA_ERASED": (
        "Данные диагностики удалены. Новую попытку можно начать через 15 минут."
    ),
    "QUICK_COMPLETE": "Быстрый результат по предмету «{subject}» готов!",
    "FULL_COMPLETE": "Полный результат по предмету «{subject}» готов!",
    "NOT_STARTED": "Начни диагностику, когда будет удобно.",
    "INCOMPLETE": "Продолжи диагностику по предмету «{subject}».",
    "RESULT_UNVIEWED": "Тебя ждёт результат по предмету «{subject}».",
    "DAY_FOLLOWUP": "Вернись к результату диагностики по предмету «{subject}».",
    "QUICK_TO_FULL": (
        "Пройди полную диагностику и загляни в «{primary_offer_label}»: "
        "{primary_offer_url}"
    ),
    "MONTH_RETEST": "Повтори диагностику по предмету «{subject}» через месяц.",
    "LIVES_REFILL": (
        "Жизни в тренажёре восстановились — продолжай готовиться!"
    ),
    "STREAK_SAVE": "Серия ещё держится. Открой план на сегодня и сохрани её.",
}


async def seed_messages(connection, school: SchoolConfig) -> None:
    """Add missing defaults while preserving administrator-edited text."""
    await connection.executemany(
        """
        INSERT INTO message_templates (key, text, description)
        VALUES ($1, $2, $3)
        ON CONFLICT (key) DO UPDATE
           SET text=CASE
                    WHEN message_templates.text=$4 THEN EXCLUDED.text
                    ELSE message_templates.text
               END,
               description=EXCLUDED.description,
               updated_at=now()
        """,
        [
            (key, text, MESSAGE_DESCRIPTIONS[key], PREVIOUS_DEFAULTS.get(key, text))
            for key, text in school.brand.messages.keyed().items()
        ],
    )


async def get_message(key: str):
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            "SELECT key, text, description, updated_at FROM message_templates WHERE key=$1",
            key,
        )


async def list_messages() -> list:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetch(
            "SELECT key, text, description, updated_at FROM message_templates ORDER BY key"
        )


async def update_message(key: str, text: str):
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            """
            UPDATE message_templates
               SET text=$2, updated_at=now()
             WHERE key=$1
            RETURNING key, text, description, updated_at
            """,
            key,
            text,
        )
