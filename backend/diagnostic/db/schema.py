"""Minimal schema owned by the diagnostic starter."""

DDL = """
CREATE TABLE IF NOT EXISTS diagnostic_erased_users (
    user_id BIGINT PRIMARY KEY,
    erased_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS diagnostic_session_generations (
    subject_key TEXT PRIMARY KEY,
    generation TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (subject_key ~ '^[0-9a-f]{64}$'),
    CHECK (generation ~ '^[0-9a-f]{32}$')
);

CREATE TABLE IF NOT EXISTS diagnostic_report_asset_bundles (
    bundle_id TEXT PRIMARY KEY,
    payload BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (octet_length(payload) BETWEEN 1 AND 26214400)
);

CREATE TABLE IF NOT EXISTS diagnostic_attempts (
    attempt_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    telegram_username TEXT,
    first_name TEXT,
    diagnostic_id TEXT NOT NULL,
    content_version TEXT NOT NULL DEFAULT '',
    exam TEXT NOT NULL,
    subject TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_progress',
    question_index INTEGER NOT NULL DEFAULT 0,
    question_count INTEGER NOT NULL,
    progress_revision BIGINT NOT NULL DEFAULT 0,
    answers JSONB NOT NULL DEFAULT '{}'::jsonb,
    correct_count INTEGER,
    score INTEGER,
    max_score INTEGER,
    score_unit TEXT,
    unassessed_part TEXT,
    strong_topics TEXT[] NOT NULL DEFAULT '{}',
    growth_topics TEXT[] NOT NULL DEFAULT '{}',
    forecast JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_asset_bundle_id TEXT,
    report_assets BYTEA,
    pdf_document BYTEA,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    result_viewed_at TIMESTAMPTZ,
    pdf_status TEXT NOT NULL DEFAULT 'pending',
    pdf_attempts INTEGER NOT NULL DEFAULT 0,
    pdf_last_error TEXT,
    pdf_locked_at TIMESTAMPTZ,
    pdf_delivered_at TIMESTAMPTZ,
    pdf_message_id BIGINT
);
ALTER TABLE diagnostic_attempts
    ADD COLUMN IF NOT EXISTS result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE diagnostic_attempts
    ADD COLUMN IF NOT EXISTS progress_revision BIGINT NOT NULL DEFAULT 0;
ALTER TABLE diagnostic_attempts
    ADD COLUMN IF NOT EXISTS report_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE diagnostic_attempts
    ADD COLUMN IF NOT EXISTS report_assets BYTEA;
ALTER TABLE diagnostic_attempts
    ADD COLUMN IF NOT EXISTS report_asset_bundle_id TEXT;
ALTER TABLE diagnostic_attempts
    ADD COLUMN IF NOT EXISTS content_version TEXT NOT NULL DEFAULT '';
ALTER TABLE diagnostic_attempts
    ADD COLUMN IF NOT EXISTS pdf_document BYTEA;
CREATE TABLE IF NOT EXISTS diagnostic_schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM diagnostic_schema_migrations
         WHERE version='2026-08-11-minimize-attempt-data'
    ) THEN
        UPDATE diagnostic_attempts
           SET telegram_username=NULL, first_name=NULL
         WHERE telegram_username IS NOT NULL OR first_name IS NOT NULL;
        UPDATE diagnostic_attempts
           SET answers='{}'::jsonb, report_snapshot='{}'::jsonb,
               report_assets=NULL, report_asset_bundle_id=NULL, pdf_document=NULL
         WHERE pdf_status IN ('sent', 'abandoned')
           AND (answers <> '{}'::jsonb OR report_snapshot <> '{}'::jsonb
                OR report_assets IS NOT NULL OR report_asset_bundle_id IS NOT NULL
                OR pdf_document IS NOT NULL);
        INSERT INTO diagnostic_schema_migrations(version)
        VALUES ('2026-08-11-minimize-attempt-data');
    END IF;
END $$;
CREATE TABLE IF NOT EXISTS diagnostic_progress_profiles (
    user_id BIGINT PRIMARY KEY,
    completion_count INTEGER NOT NULL DEFAULT 0 CHECK (completion_count >= 0),
    achievement_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS diagnostic_completion_ledger (
    attempt_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_diagnostic_attempts_user_updated
    ON diagnostic_attempts(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_diagnostic_attempts_user_started
    ON diagnostic_attempts(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_diagnostic_attempts_user_completed
    ON diagnostic_attempts(user_id, completed_at DESC)
    WHERE status = 'completed';
CREATE INDEX IF NOT EXISTS idx_diagnostic_attempts_delivery
    ON diagnostic_attempts(pdf_status, completed_at)
    WHERE status = 'completed';
CREATE INDEX IF NOT EXISTS idx_diagnostic_attempts_retention
    ON diagnostic_attempts(status, updated_at, completed_at, started_at);

CREATE TABLE IF NOT EXISTS diagnostic_engagements (
    user_id BIGINT PRIMARY KEY,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    not_started_reminder_sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_diagnostic_engagements_retention
    ON diagnostic_engagements(last_opened_at);

CREATE TABLE IF NOT EXISTS diagnostic_notifications (
    id BIGSERIAL PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    user_id BIGINT NOT NULL,
    attempt_id TEXT REFERENCES diagnostic_attempts(attempt_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempts INTEGER NOT NULL DEFAULT 0,
    locked_at TIMESTAMPTZ,
    last_error TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_diagnostic_notifications_due
    ON diagnostic_notifications(status, due_at);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM diagnostic_schema_migrations
         WHERE version='2026-08-11-retire-unversioned-attempts'
    ) THEN
        UPDATE diagnostic_attempts
           SET status='superseded', answers='{}'::jsonb, question_index=0,
               report_snapshot='{}'::jsonb, report_assets=NULL,
               report_asset_bundle_id=NULL, pdf_document=NULL, updated_at=now()
         WHERE status='in_progress' AND content_version='';
        UPDATE diagnostic_attempts
           SET pdf_status='abandoned', answers='{}'::jsonb,
               report_snapshot='{}'::jsonb, report_assets=NULL,
               report_asset_bundle_id=NULL, pdf_document=NULL,
               pdf_locked_at=NULL, updated_at=now()
         WHERE status='completed' AND content_version=''
           AND pdf_status IN ('pending', 'failed', 'sending');
        UPDATE diagnostic_notifications AS notification
           SET status='cancelled', locked_at=NULL, updated_at=now()
         WHERE notification.status IN ('pending', 'failed', 'sending')
           AND EXISTS (
               SELECT 1 FROM diagnostic_attempts AS attempt
                WHERE attempt.attempt_id=notification.attempt_id
                  AND attempt.content_version=''
           );
        INSERT INTO diagnostic_schema_migrations(version)
        VALUES ('2026-08-11-retire-unversioned-attempts');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS message_templates (
    key TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    description TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
