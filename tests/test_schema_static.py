from diagnostic.db.schema import DDL


def test_schema_contains_only_starter_tables():
    for table in (
        "diagnostic_attempts",
        "diagnostic_progress_profiles",
        "diagnostic_completion_ledger",
        "diagnostic_engagements",
        "diagnostic_offer_events",
        "diagnostic_funnel_events",
        "diagnostic_notifications",
        "diagnostic_daily_plans",
        "diagnostic_topic_progress",
        "message_templates",
        "diagnostic_content_drafts",
        "diagnostic_content_audit",
    ):
        assert "CREATE TABLE IF NOT EXISTS " + table in DDL
    assert "tenant_id" not in DDL
    assert "curator_" not in DDL


def test_offer_event_schema_excludes_raw_private_payloads():
    start = DDL.index("CREATE TABLE IF NOT EXISTS diagnostic_offer_events")
    end = DDL.index("CREATE TABLE IF NOT EXISTS diagnostic_notifications")
    offer_event_ddl = DDL[start:end]
    for forbidden in ("user_id", "init_data", "answers", "correct", "report", "url", "metadata"):
        assert forbidden not in offer_event_ddl.casefold()
    assert "event_type IN ('impression', 'click', 'dismiss')" in offer_event_ddl


def test_funnel_event_schema_stores_no_identifier_or_payload():
    start = DDL.index("CREATE TABLE IF NOT EXISTS diagnostic_funnel_events")
    end = DDL.index("CREATE INDEX IF NOT EXISTS idx_diagnostic_funnel_events_retention")
    funnel_ddl = DDL[start:end]
    for forbidden in ("user_id", "init_data", "answers", "correct", "report", "url", "metadata"):
        assert forbidden not in funnel_ddl.casefold()
    assert "subject_hash ~ '^[0-9a-f]{64}$'" in funnel_ddl
    assert "idx_diagnostic_funnel_events_day_action" in funnel_ddl


def test_funnel_action_constraints_cover_fresh_and_kir_221_schemas():
    from diagnostic.db.funnel import FUNNEL_ACTIONS

    initial_start = DDL.index("CONSTRAINT diagnostic_funnel_events_action_check")
    initial_end = DDL.index(
        "CONSTRAINT diagnostic_funnel_events_exam_length", initial_start
    )
    initial_constraint = DDL[initial_start:initial_end]

    migration_start = DDL.index(
        "version='2026-09-07-kir-221-question-skipped'"
    )
    migration_end = DDL.index(
        "INSERT INTO diagnostic_schema_migrations", migration_start
    )
    migration_constraint = DDL[migration_start:migration_end]

    for action in FUNNEL_ACTIONS:
        assert f"'{action}'" in initial_constraint
        assert f"'{action}'" in migration_constraint


def test_daily_plan_schema_is_idempotent_and_bounded():
    start = DDL.index("CREATE TABLE IF NOT EXISTS diagnostic_daily_plans")
    end = DDL.index("idx_diagnostic_daily_plans_date")
    plan_ddl = DDL[start:end]
    assert "PRIMARY KEY (user_id, plan_date)" in plan_ddl
    assert "jsonb_array_length(question_ids) BETWEEN 1 AND 10" in plan_ddl
    assert "completed_question_ids JSONB NOT NULL DEFAULT '[]'::jsonb" in plan_ddl
    for forbidden in ("correct", "answers", "init_data"):
        assert forbidden not in plan_ddl.casefold()


def test_mistake_review_columns_are_added_idempotently_with_a_migration():
    assert (
        "ALTER TABLE diagnostic_mistakes\n"
        "    ADD COLUMN IF NOT EXISTS review_count SMALLINT NOT NULL DEFAULT 0;" in DDL
    )
    assert "ADD COLUMN IF NOT EXISTS next_review_on DATE" in DDL


def test_topic_scoped_trainer_sessions_are_backward_compatible_and_bounded():
    start = DDL.index("CREATE TABLE IF NOT EXISTS diagnostic_trainer_sessions")
    end = DDL.index("CREATE INDEX IF NOT EXISTS idx_diagnostic_trainer_sessions_user_updated")
    fresh = DDL[start:end]
    assert "topic TEXT" in fresh
    assert "CHECK (topic IS NULL OR length(topic) BETWEEN 1 AND 128)" in fresh
    assert "CHECK (mode IN ('mistakes', 'today') OR topic IS NULL)" in fresh
    assert "ADD COLUMN IF NOT EXISTS topic TEXT" in fresh
    assert "topic_check" in DDL
    assert "topic_mode_check" in DDL


def test_topic_progress_table_is_additive_and_privacy_safe():
    start = DDL.index("CREATE TABLE IF NOT EXISTS diagnostic_topic_progress")
    end = DDL.index("idx_diagnostic_topic_progress_lookup")
    progress_ddl = DDL[start:end]
    assert "PRIMARY KEY (user_id, diagnostic_id, content_version, topic)" in progress_ddl
    assert "correct_question_ids JSONB NOT NULL DEFAULT '[]'::jsonb" in progress_ddl
    assert "done_at TIMESTAMPTZ" in progress_ddl
    assert "REFERENCES diagnostic_progress_profiles(user_id) ON DELETE CASCADE" in progress_ddl
    assert "content_version ~ '^[0-9a-f]{64}$'" in progress_ddl
    # No private answer content ever lands in this table.
    for forbidden in ("correct_answer", "answers", "init_data", "explanation"):
        assert forbidden not in progress_ddl.casefold()


def test_today_mode_migration_widens_trainer_modes_after_table_creation():
    assert "CHECK (mode IN ('normal', 'mistakes', 'plan', 'today'))" in DDL
    assert "2026-09-10-kir-117-today-topic-path" in DDL
    for table in ("diagnostic_trainer_sessions", "diagnostic_topic_progress"):
        assert DDL.index("CREATE TABLE IF NOT EXISTS " + table) < DDL.index(
            "2026-09-10-kir-117-today-topic-path"
        )


def test_trainer_resume_identity_includes_nullable_topic():
    from diagnostic.db import trainer

    sql = " ".join(
        constant for constant in trainer._find_resumable_session.__code__.co_consts
        if isinstance(constant, str)
    )
    assert "topic IS NOT DISTINCT FROM $6" in " ".join(sql.split())
    assert "2026-09-02-kir-173-daily-plan" in DDL
    assert "CHECK (mode IN ('normal', 'mistakes', 'plan'))" in DDL


def test_daily_plan_migration_runs_after_the_tables_it_alters():
    for table in ("diagnostic_daily_plans", "diagnostic_trainer_sessions"):
        assert DDL.index("CREATE TABLE IF NOT EXISTS " + table) < DDL.index(
            "2026-09-02-kir-173-daily-plan"
        )


def test_legacy_notification_migration_runs_after_notification_table_creation():
    create_position = DDL.index("CREATE TABLE IF NOT EXISTS diagnostic_notifications")
    migration_position = DDL.index("2026-08-11-retire-unversioned-attempts")

    assert create_position < migration_position
