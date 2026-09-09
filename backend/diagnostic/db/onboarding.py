"""First-session state belongs to the authenticated engagement record."""

from diagnostic.db.core import get_pool


async def get_status(user_id: int) -> str:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchval(
            """
            SELECT CASE
                WHEN COALESCE(p.completion_count, 0) > 0 THEN 'completed'
                WHEN e.onboarding_started_at IS NOT NULL THEN 'selection'
                ELSE 'welcome' END
              FROM diagnostic_engagements e
              LEFT JOIN diagnostic_progress_profiles p USING (user_id)
             WHERE e.user_id=$1
            """, user_id,
        ) or "welcome"


async def start_selection(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return bool(await connection.fetchval(
            """
            UPDATE diagnostic_engagements
               SET onboarding_started_at=now()
             WHERE user_id=$1 AND onboarding_started_at IS NULL
               AND NOT EXISTS (
                   SELECT 1 FROM diagnostic_progress_profiles
                    WHERE user_id=$1 AND completion_count > 0
               )
            RETURNING user_id
            """, user_id,
        ))
