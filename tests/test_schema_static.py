from diagnostic.db.schema import DDL


def test_schema_contains_only_starter_tables():
    for table in (
        "diagnostic_attempts",
        "diagnostic_progress_profiles",
        "diagnostic_completion_ledger",
        "diagnostic_engagements",
        "diagnostic_offer_events",
        "diagnostic_notifications",
        "message_templates",
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


def test_legacy_notification_migration_runs_after_notification_table_creation():
    create_position = DDL.index("CREATE TABLE IF NOT EXISTS diagnostic_notifications")
    migration_position = DDL.index("2026-08-11-retire-unversioned-attempts")

    assert create_position < migration_position
