from diagnostic.db.schema import DDL


def test_schema_contains_only_starter_tables():
    for table in (
        "diagnostic_attempts",
        "diagnostic_engagements",
        "diagnostic_notifications",
        "message_templates",
    ):
        assert "CREATE TABLE IF NOT EXISTS " + table in DDL
    assert "tenant_id" not in DDL
    assert "curator_" not in DDL


def test_legacy_notification_migration_runs_after_notification_table_creation():
    create_position = DDL.index("CREATE TABLE IF NOT EXISTS diagnostic_notifications")
    migration_position = DDL.index("2026-08-11-retire-unversioned-attempts")

    assert create_position < migration_position
