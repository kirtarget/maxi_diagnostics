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
