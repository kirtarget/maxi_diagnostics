import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio

from diagnostic.db import attempts
from diagnostic.db.core import close_db, get_pool, init_db
from diagnostic.session_identity import session_subject_key


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest_asyncio.fixture(autouse=True)
async def database():
    await init_db(os.environ["TEST_DATABASE_URL"])
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            TRUNCATE diagnostic_notifications, diagnostic_attempts,
                     diagnostic_engagements, diagnostic_erased_users,
                     diagnostic_session_generations,
                     diagnostic_report_asset_bundles
            RESTART IDENTITY CASCADE
            """
        )
    yield
    await close_db()


def completion(
    attempt_id: str,
    *,
    answers: dict[str, object],
    mode: str = "quick",
    user_id: int = 101,
    subject: str = "math",
    progress_revision: int = 1,
    result_snapshot: dict[str, object] | None = None,
    report_snapshot: dict[str, object] | None = None,
):
    return attempts.AttemptCompletion(
        attempt_id=attempt_id,
        user_id=user_id,
        diagnostic_id="math-10",
        content_version="a" * 64,
        exam="ege",
        subject=subject,
        mode=mode,
        question_count=2,
        progress_revision=progress_revision,
        answers=answers,
        correct_count=1,
        score=50,
        max_score=100,
        score_unit="points",
        unassessed_part=None,
        strong_topics=["algebra"],
        growth_topics=["geometry"],
        forecast={"target": 70},
        result_snapshot=result_snapshot or {"score": 50},
        report_snapshot=report_snapshot or {},
    )


@pytest.mark.asyncio
async def test_completion_is_idempotent_and_notification_dedupe_is_unique():
    attempt_id = f"attempt-{uuid4()}"
    first = await attempts.complete_attempt(
        completion(attempt_id, answers={"q1": "A"}, result_snapshot={"score": 50})
    )
    second = await attempts.complete_attempt(
        completion(attempt_id, answers={"q1": "B"}, result_snapshot={"score": 0})
    )

    assert first["answers"] == {"q1": "A"}
    assert second["answers"] == {"q1": "A"}
    assert second["result_snapshot"] == {"score": 50}

    notifications = await attempts.list_notifications(attempt_id)
    assert {row["kind"] for row in notifications} == {
        "result_unviewed",
        "day_followup",
        "quick_to_full",
        "month_retest",
    }
    assert len({row["dedupe_key"] for row in notifications}) == 4


@pytest.mark.asyncio
async def test_review_read_is_owner_scoped_and_keeps_first_snapshot():
    attempt_id = f"attempt-{uuid4()}"
    first_snapshot = {"review_snapshot": [{"question_id": "q1", "expected_answer": "4"}]}
    second_snapshot = {"review_snapshot": [{"question_id": "q1", "expected_answer": "5"}]}

    await attempts.complete_attempt(completion(
        attempt_id, answers={"q1": "2"}, user_id=101, report_snapshot=first_snapshot,
    ))
    await attempts.complete_attempt(completion(
        attempt_id, answers={"q1": "3"}, user_id=101, report_snapshot=second_snapshot,
    ))

    owner_row = await attempts.get_review_attempt(attempt_id, 101)
    stranger_row = await attempts.get_review_attempt(attempt_id, 202)

    assert owner_row is not None
    assert owner_row["report_snapshot"] == first_snapshot
    assert stranger_row is None


@pytest.mark.asyncio
async def test_direct_completion_counts_against_the_hourly_start_budget():
    user_id = 8_100_000_000 + uuid4().int % 100_000_000
    for _ in range(10):
        await attempts.complete_attempt(
            completion(f"attempt-{uuid4()}", answers={"q1": "A"}, user_id=user_id)
        )

    with pytest.raises(ValueError, match="diagnostic_rate_limited"):
        await attempts.complete_attempt(
            completion(f"attempt-{uuid4()}", answers={"q1": "A"}, user_id=user_id)
        )


@pytest.mark.asyncio
async def test_view_transition_cancels_even_an_inflight_unviewed_reminder():
    attempt_id = f"attempt-{uuid4()}"
    user_id = 8_200_000_000 + uuid4().int % 100_000_000
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}, user_id=user_id))
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_notifications SET status='sending', locked_at=now() WHERE attempt_id=$1 AND kind='result_unviewed'",
            attempt_id,
        )

    viewed = await attempts.mark_result_viewed(attempt_id, user_id)
    notification = next(
        row for row in await attempts.list_notifications(attempt_id)
        if row["kind"] == "result_unviewed"
    )

    assert viewed["viewed_transition"] is True
    assert notification["status"] == "cancelled"
    assert notification["locked_at"] is None


@pytest.mark.asyncio
async def test_later_full_completion_cancels_inflight_quick_to_full_for_same_diagnostic():
    user_id = 8_300_000_000 + uuid4().int % 100_000_000
    quick_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(
        completion(quick_id, answers={"q1": "A"}, user_id=user_id, mode="quick")
    )
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_notifications SET status='sending', locked_at=now() WHERE attempt_id=$1 AND kind='quick_to_full'",
            quick_id,
        )

    await attempts.complete_attempt(
        completion(f"attempt-{uuid4()}", answers={"q1": "A"}, user_id=user_id, mode="full")
    )
    quick_to_full = next(
        row for row in await attempts.list_notifications(quick_id)
        if row["kind"] == "quick_to_full"
    )

    assert quick_to_full["status"] == "cancelled"
    assert quick_to_full["locked_at"] is None


@pytest.mark.asyncio
async def test_erasure_tombstone_prevents_progress_completion_and_reopen():
    from diagnostic.admin.repository import delete_diagnostic_user

    user_id = 8_000_000_000 + uuid4().int % 1_000_000_000
    attempt_id = f"attempt-{uuid4()}"
    progress = attempts.AttemptProgress(
        attempt_id=attempt_id,
        user_id=user_id,
        diagnostic_id="math-10",
        content_version="a" * 64,
        exam="ege",
        subject="math",
        mode="quick",
        question_index=0,
        question_count=2,
        answers={},
    )
    await attempts.upsert_progress(progress)
    await delete_diagnostic_user(user_id, "a" * 64, "b" * 32)

    with pytest.raises(ValueError, match="diagnostic_user_erased"):
        await attempts.upsert_progress(progress)
    with pytest.raises(ValueError, match="diagnostic_user_erased"):
        await attempts.complete_attempt(completion(f"attempt-{uuid4()}", answers={"q1": "A"}, user_id=user_id))
    with pytest.raises(ValueError, match="diagnostic_user_erased"):
        await attempts.mark_opened(user_id)

    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_erased_users SET erased_at=now() - interval '16 minutes' WHERE user_id=$1",
            user_id,
        )
    assert await attempts.mark_opened(user_id) is True
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_erased_users WHERE user_id=$1", user_id
        ) == 0


@pytest.mark.asyncio
async def test_progress_cannot_replace_completed_attempt_owned_by_same_user():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))

    progress = attempts.AttemptProgress(
        attempt_id=attempt_id,
        user_id=101,
        diagnostic_id="math-10",
        content_version="a" * 64,
        exam="ege",
        subject="math",
        mode="quick",
        question_index=1,
        question_count=2,
        answers={"q1": "B"},
    )
    row = await attempts.upsert_progress(progress)

    assert row["status"] == "completed"
    assert row["answers"] == {"q1": "A"}


@pytest.mark.asyncio
async def test_retention_supersedes_stale_progress_and_expires_old_history():
    secret = "stable-installation-secret-1234567890"
    stale_user = 8_400_000_000 + uuid4().int % 100_000_000
    expired_user = 8_500_000_000 + uuid4().int % 100_000_000
    stale_id = f"attempt-{uuid4()}"
    expired_id = f"attempt-{uuid4()}"
    await attempts.upsert_progress(attempts.AttemptProgress(
        attempt_id=stale_id,
        user_id=stale_user,
        diagnostic_id="math-10",
        content_version="a" * 64,
        exam="ege",
        subject="math",
        mode="quick",
        question_index=1,
        question_count=2,
        answers={"q1": "A"},
    ))
    await attempts.complete_attempt(
        completion(expired_id, answers={"q1": "A"}, user_id=expired_user)
    )
    subject_key = session_subject_key(secret, expired_user)
    old_generation = await attempts.get_or_create_session_generation(subject_key, "1" * 32)
    await attempts.mark_opened(expired_user)
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_attempts SET updated_at=now() - interval '31 days' WHERE attempt_id=$1",
            stale_id,
        )
        await connection.execute(
            "UPDATE diagnostic_attempts SET completed_at=now() - interval '366 days', updated_at=now() - interval '366 days' WHERE attempt_id=$1",
            expired_id,
        )
        await connection.execute(
            "UPDATE diagnostic_engagements SET last_opened_at=now() - interval '366 days' WHERE user_id=$1",
            expired_user,
        )

    counts = await attempts.purge_retained_diagnostic_data(secret, 365, 30)

    stale = await attempts.get_attempt(stale_id, stale_user)
    assert stale["status"] == "superseded"
    assert stale["answers"] == {}
    assert await attempts.get_attempt(expired_id, expired_user) is None
    assert await attempts.get_session_generation(subject_key) != old_generation
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_engagements WHERE user_id=$1", expired_user
        ) == 0
    assert counts["superseded"] >= 1
    assert counts["deleted_attempts"] >= 1


@pytest.mark.asyncio
async def test_claims_transition_pending_work_to_sending_once():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))

    claimed_pdf = await attempts.claim_pending_pdf(attempt_id)
    assert claimed_pdf is not None
    assert claimed_pdf["pdf_status"] == "sending"
    assert claimed_pdf["pdf_attempts"] == 1
    assert await attempts.claim_pending_pdf(attempt_id) is None

    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_notifications SET due_at=now() - interval '1 minute' WHERE attempt_id=$1",
            attempt_id,
        )
    notifications = await attempts.claim_due_notifications()

    assert len(notifications) == 1
    assert {row["status"] for row in notifications} == {"sending"}
    assert {row["attempts"] for row in notifications} == {1}


@pytest.mark.asyncio
async def test_first_pdf_claim_can_store_document_without_waiting_for_stale_reclaim():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))
    claimed = await attempts.claim_pending_pdf(attempt_id)

    assert claimed is not None
    assert await attempts.store_pdf_document(
        attempt_id, claimed["pdf_locked_at"], b"%PDF-first-claim"
    ) is True

    pool = await get_pool()
    async with pool.acquire() as connection:
        stored = await connection.fetchrow(
            "SELECT pdf_document, answers, report_snapshot FROM diagnostic_attempts WHERE attempt_id=$1",
            attempt_id,
        )
    assert stored["pdf_document"] == b"%PDF-first-claim"
    assert stored["answers"] == {}
    assert stored["report_snapshot"] == {}


@pytest.mark.asyncio
async def test_repeat_completion_uses_the_original_full_result_for_followups():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(
        completion(attempt_id, answers={"q1": "A"}, mode="full", subject="physics")
    )
    repeated = await attempts.complete_attempt(
        completion(attempt_id, answers={"q1": "B"}, mode="quick", subject="chemistry")
    )

    notifications = await attempts.list_notifications(attempt_id)

    assert repeated["mode"] == "full"
    assert repeated["subject"] == "physics"
    assert {row["kind"] for row in notifications} == {
        "result_unviewed",
        "day_followup",
        "month_retest",
    }
    assert {row["payload"]["mode"] for row in notifications} == {"full"}
    assert {row["payload"]["subject"] for row in notifications} == {"physics"}


@pytest.mark.asyncio
async def test_late_progress_after_completion_leaves_incomplete_cancelled():
    attempt_id = f"attempt-{uuid4()}"
    progress = attempts.AttemptProgress(
        attempt_id=attempt_id,
        user_id=101,
        diagnostic_id="math-10",
        content_version="a" * 64,
        exam="ege",
        subject="math",
        mode="quick",
        question_index=1,
        question_count=2,
        answers={"q1": "A"},
    )
    await attempts.upsert_progress(progress)
    await attempts.complete_attempt(
        completion(attempt_id, answers={"q1": "A"}, progress_revision=2)
    )
    await attempts.upsert_progress(progress)

    notifications = await attempts.list_notifications(attempt_id)
    incomplete = [row for row in notifications if row["kind"] == "incomplete"]

    assert len(incomplete) == 1
    assert incomplete[0]["status"] == "cancelled"
    assert incomplete[0]["payload"] == {"mode": "quick"}


@pytest.mark.asyncio
async def test_attempt_cannot_be_mutated_by_a_different_owner():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))
    other_progress = attempts.AttemptProgress(
        attempt_id=attempt_id,
        user_id=202,
        diagnostic_id="math-10",
        content_version="a" * 64,
        exam="ege",
        subject="math",
        mode="quick",
        question_index=1,
        question_count=2,
        answers={"q1": "B"},
    )

    with pytest.raises(ValueError, match="diagnostic_attempt_conflict"):
        await attempts.upsert_progress(other_progress)
    with pytest.raises(ValueError, match="diagnostic_attempt_conflict"):
        await attempts.complete_attempt(completion(attempt_id, answers={"q1": "B"}, user_id=202))


@pytest.mark.asyncio
async def test_old_pdf_lease_cannot_finalize_a_reclaimed_delivery():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))
    first_claim = await attempts.claim_pending_pdf(attempt_id)
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_attempts SET pdf_locked_at=now() - interval '11 minutes' WHERE attempt_id=$1",
            attempt_id,
        )
    second_claim = await attempts.claim_pending_pdf(attempt_id)

    assert second_claim is not None
    assert second_claim["pdf_locked_at"] != first_claim["pdf_locked_at"]
    assert await attempts.mark_pdf_delivered(attempt_id, first_claim["pdf_locked_at"], 11) is False
    assert (await attempts.get_attempt(attempt_id))["pdf_status"] == "sending"
    assert await attempts.mark_pdf_delivered(attempt_id, second_claim["pdf_locked_at"], 22) is True
    assert (await attempts.get_attempt(attempt_id))["pdf_message_id"] == 22


@pytest.mark.asyncio
async def test_old_notification_failure_cannot_overwrite_terminal_states():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_notifications SET due_at=now() - interval '1 minute' WHERE attempt_id=$1",
            attempt_id,
        )
    claims = []
    for _ in range(3):
        claims.extend(await attempts.claim_due_notifications())
    sent = claims[0]
    cancelled = claims[1]
    abandoned = claims[2]
    assert await attempts.mark_notification_sent(sent["id"], sent["locked_at"]) is True
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_notifications SET status='cancelled', locked_at=NULL WHERE id=$1",
            cancelled["id"],
        )
        await connection.execute(
            "UPDATE diagnostic_notifications SET status='abandoned', locked_at=NULL WHERE id=$1",
            abandoned["id"],
        )

    assert await attempts.mark_notification_failed(sent["id"], sent["locked_at"], "late") is False
    assert await attempts.mark_notification_failed(cancelled["id"], cancelled["locked_at"], "late") is False
    assert await attempts.mark_notification_failed(abandoned["id"], abandoned["locked_at"], "late") is False

    async with pool.acquire() as connection:
        states = await connection.fetch(
            "SELECT id, status FROM diagnostic_notifications WHERE id = ANY($1::bigint[])",
            [sent["id"], cancelled["id"], abandoned["id"]],
        )
    assert {row["status"] for row in states} == {"sent", "cancelled", "abandoned"}


@pytest.mark.asyncio
async def test_old_pdf_failure_cannot_overwrite_terminal_states():
    pool = await get_pool()
    cases = []
    for status in ("sent", "cancelled", "abandoned"):
        attempt_id = f"attempt-{uuid4()}"
        await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))
        claim = await attempts.claim_pending_pdf(attempt_id)
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE diagnostic_attempts SET pdf_status=$2, pdf_locked_at=NULL WHERE attempt_id=$1",
                attempt_id,
                status,
            )
        cases.append((attempt_id, claim["pdf_locked_at"], status))

    for attempt_id, lease, expected_status in cases:
        assert await attempts.mark_pdf_failed(attempt_id, lease, "late") is False
        assert (await attempts.get_attempt(attempt_id))["pdf_status"] == expected_status


@pytest.mark.asyncio
async def test_pdf_retry_windows_and_eighth_failure_abandons_with_bounded_error():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))
    first_claim = await attempts.claim_pending_pdf(attempt_id)
    assert await attempts.mark_pdf_failed(attempt_id, first_claim["pdf_locked_at"], "x" * 2000) is True
    assert await attempts.claim_pending_pdf(attempt_id) is None

    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_attempts SET updated_at=now() - interval '6 minutes' WHERE attempt_id=$1",
            attempt_id,
        )
    retried = await attempts.claim_pending_pdf(attempt_id)
    assert retried is not None

    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_attempts SET pdf_attempts=7, pdf_status='pending', pdf_locked_at=NULL, pdf_document=$2 WHERE attempt_id=$1",
            attempt_id,
            b"%PDF-retained-until-terminal",
        )
    eighth_claim = await attempts.claim_pending_pdf(attempt_id)
    assert eighth_claim["pdf_attempts"] == 8
    assert await attempts.mark_pdf_failed(attempt_id, eighth_claim["pdf_locked_at"], "x" * 2000) is True
    final = await attempts.get_attempt(attempt_id)
    assert final["pdf_status"] == "abandoned"
    assert len(final["pdf_last_error"]) == 1000
    assert await attempts.claim_pending_pdf(attempt_id) is None
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT pdf_document IS NULL FROM diagnostic_attempts WHERE attempt_id=$1",
            attempt_id,
        ) is True


@pytest.mark.asyncio
async def test_viewing_result_does_not_postpone_a_due_pdf_retry():
    attempt_id = f"attempt-{uuid4()}"
    user_id = 8_100_000_000 + uuid4().int % 100_000_000
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}, user_id=user_id))
    claim = await attempts.claim_pending_pdf(attempt_id)
    await attempts.mark_pdf_failed(attempt_id, claim["pdf_locked_at"], "temporary")
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_attempts SET updated_at=now() - interval '6 minutes' WHERE attempt_id=$1",
            attempt_id,
        )

    await attempts.mark_result_viewed(attempt_id, user_id)

    assert await attempts.claim_pending_pdf(attempt_id) is not None


@pytest.mark.asyncio
async def test_successful_pdf_delivery_clears_retained_document_bytes():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))
    claim = await attempts.claim_pending_pdf(attempt_id)
    await attempts.store_pdf_document(attempt_id, claim["pdf_locked_at"], b"%PDF-document")
    assert await attempts.mark_pdf_delivered(attempt_id, claim["pdf_locked_at"], 77) is True

    pool = await get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """SELECT pdf_document IS NULL AS pdf_cleared,
                      answers = '{}'::jsonb AS answers_cleared,
                      report_snapshot = '{}'::jsonb AS snapshot_cleared,
                      report_asset_bundle_id IS NULL AS bundle_released
                   FROM diagnostic_attempts WHERE attempt_id=$1""",
            attempt_id,
        )
        assert dict(row) == {
            "pdf_cleared": True,
            "answers_cleared": True,
            "snapshot_cleared": True,
            "bundle_released": True,
        }


@pytest.mark.asyncio
async def test_notification_retries_after_five_minutes_and_reclaims_after_ten():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))
    pool = await get_pool()
    async with pool.acquire() as connection:
        notification_id = await connection.fetchval(
            "SELECT id FROM diagnostic_notifications WHERE attempt_id=$1 ORDER BY id LIMIT 1",
            attempt_id,
        )
        await connection.execute(
            "UPDATE diagnostic_notifications SET due_at=now() - interval '1 minute' WHERE id=$1",
            notification_id,
        )
    first_claim = (await attempts.claim_due_notifications())[0]
    assert first_claim["id"] == notification_id
    assert await attempts.mark_notification_failed(first_claim["id"], first_claim["locked_at"], "retry") is True
    assert first_claim["id"] not in {row["id"] for row in await attempts.claim_due_notifications()}

    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_notifications SET updated_at=now() - interval '6 minutes' WHERE id=$1",
            first_claim["id"],
        )
    second_claim = next(
        row for row in await attempts.claim_due_notifications() if row["id"] == first_claim["id"]
    )
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_notifications SET locked_at=now() - interval '11 minutes' WHERE id=$1",
            second_claim["id"],
        )
    third_claim = next(
        row for row in await attempts.claim_due_notifications() if row["id"] == first_claim["id"]
    )

    assert second_claim["attempts"] == 2
    assert third_claim["attempts"] == 3
    assert third_claim["locked_at"] != second_claim["locked_at"]
    assert await attempts.mark_notification_sent(second_claim["id"], second_claim["locked_at"]) is False
    assert await attempts.mark_notification_sent(third_claim["id"], third_claim["locked_at"]) is True


@pytest.mark.asyncio
async def test_claimed_notification_context_and_cancel_require_exact_lease():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute("UPDATE diagnostic_notifications SET due_at=now() - interval '1 minute' WHERE attempt_id=$1", attempt_id)
    claim = (await attempts.claim_due_notifications(limit=1))[0]

    assert await attempts.get_claimed_notification(claim["id"], claim["locked_at"]) is not None
    assert await attempts.get_claimed_notification(claim["id"], claim["locked_at"].replace(year=2025)) is None
    assert await attempts.cancel_notification(claim["id"], claim["locked_at"].replace(year=2025)) is False
    assert await attempts.cancel_notification(claim["id"], claim["locked_at"]) is True
    assert await attempts.get_claimed_notification(claim["id"], claim["locked_at"]) is None


@pytest.mark.asyncio
async def test_pdf_claim_tick_abandons_only_stale_exhausted_sending_lease():
    pool = await get_pool()
    ids = {name: f"attempt-{name}-{uuid4()}" for name in ("stale8", "fresh8", "stale7", "sent")}
    for attempt_id in ids.values():
        await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_attempts SET pdf_status='sending', pdf_attempts=8, pdf_locked_at=now() - interval '11 minutes' WHERE attempt_id=$1",
            ids["stale8"],
        )
        await connection.execute(
            "UPDATE diagnostic_attempts SET pdf_status='sending', pdf_attempts=8, pdf_locked_at=now() WHERE attempt_id=$1",
            ids["fresh8"],
        )
        await connection.execute(
            "UPDATE diagnostic_attempts SET pdf_status='sending', pdf_attempts=7, pdf_locked_at=now() - interval '11 minutes' WHERE attempt_id=$1",
            ids["stale7"],
        )
        await connection.execute(
            "UPDATE diagnostic_attempts SET pdf_status='sent', pdf_attempts=8, pdf_locked_at=NULL WHERE attempt_id=$1",
            ids["sent"],
        )

    assert await asyncio.gather(
        attempts.claim_pending_pdf(ids["stale8"]),
        attempts.claim_pending_pdf(ids["stale8"]),
    ) == [None, None]
    reclaimed = await attempts.claim_pending_pdf(ids["stale7"])
    rows = {name: await attempts.get_attempt(attempt_id) for name, attempt_id in ids.items()}

    assert rows["stale8"]["pdf_status"] == "abandoned"
    assert rows["stale8"]["pdf_locked_at"] is None
    assert rows["stale8"]["pdf_last_error"] == "retry_limit_reached"
    assert rows["fresh8"]["pdf_status"] == "sending"
    assert rows["fresh8"]["pdf_attempts"] == 8
    assert reclaimed["attempt_id"] == ids["stale7"]
    assert reclaimed["pdf_attempts"] == 8
    assert rows["sent"]["pdf_status"] == "sent"


@pytest.mark.asyncio
async def test_notification_claim_tick_abandons_only_stale_exhausted_sending_lease():
    attempt_id = f"attempt-{uuid4()}"
    await attempts.complete_attempt(completion(attempt_id, answers={"q1": "A"}))
    pool = await get_pool()
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            "SELECT id FROM diagnostic_notifications WHERE attempt_id=$1 ORDER BY id",
            attempt_id,
        )
        ids = [row["id"] for row in rows[:4]]
        await connection.execute(
            "UPDATE diagnostic_notifications SET due_at=now() + interval '1 day' WHERE attempt_id=$1",
            attempt_id,
        )
        await connection.execute(
            "UPDATE diagnostic_notifications SET status='sending', attempts=8, due_at=now() - interval '1 minute', locked_at=now() - interval '11 minutes' WHERE id=$1",
            ids[0],
        )
        await connection.execute(
            "UPDATE diagnostic_notifications SET status='sending', attempts=8, due_at=now() - interval '1 minute', locked_at=now() WHERE id=$1",
            ids[1],
        )
        await connection.execute(
            "UPDATE diagnostic_notifications SET status='sending', attempts=7, due_at=now() - interval '1 minute', locked_at=now() - interval '11 minutes' WHERE id=$1",
            ids[2],
        )
        await connection.execute(
            "UPDATE diagnostic_notifications SET status='sent', attempts=8, due_at=now() - interval '1 minute', locked_at=NULL WHERE id=$1",
            ids[3],
        )

    claimed = await attempts.claim_due_notifications(limit=20)
    async with pool.acquire() as connection:
        states = await connection.fetch(
            "SELECT id, status, attempts, locked_at, last_error FROM diagnostic_notifications WHERE id = ANY($1::bigint[])",
            ids,
        )
    by_id = {row["id"]: row for row in states}

    target_claims = [row for row in claimed if row["id"] in ids]
    assert [row["id"] for row in target_claims] == [ids[2]]
    assert target_claims[0]["attempts"] == 8
    assert by_id[ids[0]]["status"] == "abandoned"
    assert by_id[ids[0]]["locked_at"] is None
    assert by_id[ids[0]]["last_error"] == "retry_limit_reached"
    assert by_id[ids[1]]["status"] == "sending"
    assert by_id[ids[1]]["attempts"] == 8
    assert by_id[ids[3]]["status"] == "sent"
