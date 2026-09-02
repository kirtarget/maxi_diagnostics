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
    xp_total BIGINT NOT NULL DEFAULT 0 CHECK (xp_total >= 0),
    streak_days INTEGER NOT NULL DEFAULT 0 CHECK (streak_days >= 0),
    streak_last_date DATE,
    lives_remaining SMALLINT NOT NULL DEFAULT 5 CHECK (lives_remaining BETWEEN 0 AND 5),
    lives_refill_at TIMESTAMPTZ,
    daily_goal_target SMALLINT NOT NULL DEFAULT 1 CHECK (daily_goal_target BETWEEN 1 AND 100),
    daily_goal_progress SMALLINT NOT NULL DEFAULT 0 CHECK (daily_goal_progress >= 0),
    daily_goal_date DATE,
    quest_key TEXT,
    quest_progress SMALLINT NOT NULL DEFAULT 0 CHECK (quest_progress >= 0),
    quest_target SMALLINT CHECK (quest_target IS NULL OR quest_target BETWEEN 1 AND 100),
    quest_date DATE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS diagnostic_completion_ledger (
    attempt_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- KIR-91 intentionally starts a new gameplay ledger at deployment time. Historical
-- completion rows are retained, but are not awarded retroactively without a validated
-- deployment timezone and a transactional projection rebuild.
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS xp_total BIGINT NOT NULL DEFAULT 0;
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS streak_days INTEGER NOT NULL DEFAULT 0;
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS streak_last_date DATE;
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS lives_remaining SMALLINT NOT NULL DEFAULT 5;
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS lives_refill_at TIMESTAMPTZ;
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS daily_goal_target SMALLINT NOT NULL DEFAULT 1;
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS daily_goal_progress SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS daily_goal_date DATE;
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS quest_key TEXT;
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS quest_progress SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS quest_target SMALLINT;
ALTER TABLE diagnostic_progress_profiles
    ADD COLUMN IF NOT EXISTS quest_date DATE;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='diagnostic_progress_profiles_xp_total_check') THEN
        ALTER TABLE diagnostic_progress_profiles
            ADD CONSTRAINT diagnostic_progress_profiles_xp_total_check CHECK (xp_total >= 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='diagnostic_progress_profiles_streak_days_check') THEN
        ALTER TABLE diagnostic_progress_profiles
            ADD CONSTRAINT diagnostic_progress_profiles_streak_days_check CHECK (streak_days >= 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='diagnostic_progress_profiles_lives_remaining_check') THEN
        ALTER TABLE diagnostic_progress_profiles
            ADD CONSTRAINT diagnostic_progress_profiles_lives_remaining_check CHECK (lives_remaining BETWEEN 0 AND 5);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='diagnostic_progress_profiles_daily_goal_target_check') THEN
        ALTER TABLE diagnostic_progress_profiles
            ADD CONSTRAINT diagnostic_progress_profiles_daily_goal_target_check CHECK (daily_goal_target BETWEEN 1 AND 100);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='diagnostic_progress_profiles_daily_goal_progress_check') THEN
        ALTER TABLE diagnostic_progress_profiles
            ADD CONSTRAINT diagnostic_progress_profiles_daily_goal_progress_check CHECK (daily_goal_progress BETWEEN 0 AND daily_goal_target);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='diagnostic_progress_profiles_quest_progress_check') THEN
        ALTER TABLE diagnostic_progress_profiles
            ADD CONSTRAINT diagnostic_progress_profiles_quest_progress_check
            CHECK (quest_progress >= 0 AND (quest_target IS NULL OR quest_progress <= quest_target));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='diagnostic_progress_profiles_quest_target_check') THEN
        ALTER TABLE diagnostic_progress_profiles
            ADD CONSTRAINT diagnostic_progress_profiles_quest_target_check
            CHECK (quest_target IS NULL OR quest_target BETWEEN 1 AND 100);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS diagnostic_trainer_sessions (
    session_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES diagnostic_progress_profiles(user_id) ON DELETE CASCADE,
    diagnostic_id TEXT NOT NULL,
    content_version TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'normal',
    source_attempt_id TEXT REFERENCES diagnostic_attempts(attempt_id) ON DELETE CASCADE,
    selected_question_ids JSONB NOT NULL,
    current_index INTEGER NOT NULL DEFAULT 0 CHECK (current_index >= 0),
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    status TEXT NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CHECK (session_id ~ '^[A-Za-z0-9_-]{32,64}$'),
    CHECK (content_version ~ '^[0-9a-f]{64}$'),
    CHECK (mode IN ('normal', 'mistakes')),
    CHECK ((mode = 'mistakes') = (source_attempt_id IS NOT NULL)),
    CHECK (status IN ('active', 'completed', 'exhausted')),
    CHECK (jsonb_typeof(selected_question_ids) = 'array'),
    CHECK (jsonb_array_length(selected_question_ids) BETWEEN 1 AND 200),
    CHECK (status <> 'completed' OR completed_at IS NOT NULL)
);
ALTER TABLE diagnostic_trainer_sessions
    ADD COLUMN IF NOT EXISTS source_attempt_id TEXT REFERENCES diagnostic_attempts(attempt_id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_diagnostic_trainer_sessions_user_updated
    ON diagnostic_trainer_sessions(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS diagnostic_trainer_answers (
    answer_id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES diagnostic_trainer_sessions(session_id) ON DELETE CASCADE,
    question_id TEXT NOT NULL,
    answer JSONB NOT NULL,
    revision BIGINT NOT NULL CHECK (revision >= 1),
    next_revision BIGINT NOT NULL CHECK (next_revision > revision),
    idempotency_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    public_feedback JSONB NOT NULL DEFAULT '{}'::jsonb,
    xp_delta INTEGER NOT NULL DEFAULT 0 CHECK (xp_delta BETWEEN 0 AND 10),
    life_delta SMALLINT NOT NULL DEFAULT 0 CHECK (life_delta BETWEEN -1 AND 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, question_id),
    UNIQUE (session_id, idempotency_key),
    CHECK (length(idempotency_key) BETWEEN 1 AND 128),
    CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    CHECK (octet_length(convert_to(answer::text, 'UTF8')) <= 16384),
    CHECK (octet_length(convert_to(public_feedback::text, 'UTF8')) <= 8192)
);
CREATE INDEX IF NOT EXISTS idx_diagnostic_trainer_answers_session_revision
    ON diagnostic_trainer_answers(session_id, revision);

CREATE TABLE IF NOT EXISTS diagnostic_mistakes (
    user_id BIGINT NOT NULL REFERENCES diagnostic_progress_profiles(user_id) ON DELETE CASCADE,
    diagnostic_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    source_attempt_id TEXT NOT NULL REFERENCES diagnostic_attempts(attempt_id) ON DELETE CASCADE,
    source_content_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, diagnostic_id, question_id),
    CHECK (source_content_version ~ '^[0-9a-f]{64}$')
);
CREATE INDEX IF NOT EXISTS idx_diagnostic_mistakes_unresolved
    ON diagnostic_mistakes(user_id, diagnostic_id, resolved_at, created_at);

CREATE TABLE IF NOT EXISTS diagnostic_progress_events (
    event_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    idempotency_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    activity_date DATE NOT NULL,
    xp_delta INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT diagnostic_progress_events_key_length
        CHECK (length(idempotency_key) BETWEEN 1 AND 128),
    CONSTRAINT diagnostic_progress_events_fingerprint_shape
        CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT diagnostic_progress_events_event_type_check
        CHECK (event_type IN (
            'diagnostic_quick_completed', 'diagnostic_full_completed',
            'trainer_answer_correct', 'trainer_session_completed', 'quest_rewarded'
        )),
    CONSTRAINT diagnostic_progress_events_source_type_check
        CHECK (source_type IN ('diagnostic_completion', 'trainer_answer', 'trainer_session', 'quest_reward')),
    CONSTRAINT diagnostic_progress_events_source_id_length
        CHECK (length(source_id) BETWEEN 1 AND 256),
    CONSTRAINT diagnostic_progress_events_xp_delta_check
        CHECK (xp_delta BETWEEN -1000 AND 1000),
    UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_diagnostic_progress_events_user_date
    ON diagnostic_progress_events(user_id, activity_date DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_diagnostic_progress_events_date_type
    ON diagnostic_progress_events(activity_date, event_type, user_id);

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

CREATE TABLE IF NOT EXISTS diagnostic_offer_events (
    event_id TEXT PRIMARY KEY,
    subject_hash TEXT NOT NULL,
    placement TEXT NOT NULL,
    offer_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT diagnostic_offer_events_id_length
        CHECK (length(event_id) BETWEEN 16 AND 128),
    CONSTRAINT diagnostic_offer_events_subject_hash_shape
        CHECK (subject_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT diagnostic_offer_events_placement_shape
        CHECK (placement ~ '^[a-z][a-z0-9_-]{0,31}$'),
    CONSTRAINT diagnostic_offer_events_offer_id_shape
        CHECK (offer_id ~ '^[a-z0-9][a-z0-9_-]{0,31}$'),
    CONSTRAINT diagnostic_offer_events_type_check
        CHECK (event_type IN ('impression', 'click', 'dismiss')),
    CONSTRAINT diagnostic_offer_events_fingerprint_shape
        CHECK (fingerprint ~ '^[0-9a-f]{64}$')
);
CREATE INDEX IF NOT EXISTS idx_diagnostic_offer_events_subject_time
    ON diagnostic_offer_events(subject_hash, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_diagnostic_offer_events_retention
    ON diagnostic_offer_events(occurred_at);

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

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM diagnostic_schema_migrations
         WHERE version='2026-08-25-kir-92-trainer-v1'
    ) THEN
        ALTER TABLE diagnostic_progress_events
            DROP CONSTRAINT IF EXISTS diagnostic_progress_events_event_type_check;
        ALTER TABLE diagnostic_progress_events
            ADD CONSTRAINT diagnostic_progress_events_event_type_check
            CHECK (event_type IN (
                'diagnostic_quick_completed', 'diagnostic_full_completed',
                'trainer_answer_correct', 'trainer_session_completed', 'quest_rewarded'
            ));
        ALTER TABLE diagnostic_progress_events
            DROP CONSTRAINT IF EXISTS diagnostic_progress_events_source_type_check;
        ALTER TABLE diagnostic_progress_events
            ADD CONSTRAINT diagnostic_progress_events_source_type_check
            CHECK (source_type IN (
                'diagnostic_completion', 'trainer_answer', 'trainer_session', 'quest_reward'
            ));
        INSERT INTO diagnostic_schema_migrations(version)
        VALUES ('2026-08-25-kir-92-trainer-v1');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM diagnostic_schema_migrations
         WHERE version='2026-08-25-kir-92-mistakes-v1'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
             WHERE conname='diagnostic_trainer_sessions_mode_source_check'
        ) THEN
            ALTER TABLE diagnostic_trainer_sessions
                ADD CONSTRAINT diagnostic_trainer_sessions_mode_source_check
                CHECK ((mode='mistakes')=(source_attempt_id IS NOT NULL));
        END IF;
        INSERT INTO diagnostic_schema_migrations(version)
        VALUES ('2026-08-25-kir-92-mistakes-v1');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS message_templates (
    key TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    description TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS diagnostic_content_drafts (
    diagnostic_id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    edit_revision BIGINT NOT NULL DEFAULT 1 CHECK (edit_revision >= 1),
    base_content_version TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (diagnostic_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$'),
    CHECK (base_content_version ~ '^[0-9a-f]{64}$'),
    CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (length(created_by) BETWEEN 1 AND 128),
    CHECK (length(updated_by) BETWEEN 1 AND 128),
    CHECK (jsonb_typeof(payload) = 'object'),
    CHECK (octet_length(convert_to(payload::text, 'UTF8')) <= 1048576)
);

CREATE TABLE IF NOT EXISTS diagnostic_content_audit (
    event_id BIGSERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    diagnostic_id TEXT NOT NULL,
    question_id TEXT,
    edit_revision BIGINT NOT NULL CHECK (edit_revision >= 1),
    before_hash TEXT NOT NULL,
    after_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (action IN (
        'draft_created', 'question_created', 'question_updated',
        'validated', 'exported'
    )),
    CHECK (length(actor) BETWEEN 1 AND 128),
    CHECK (diagnostic_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$'),
    CHECK (question_id IS NULL OR question_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'),
    CHECK (before_hash ~ '^[0-9a-f]{64}$'),
    CHECK (after_hash ~ '^[0-9a-f]{64}$')
);
CREATE INDEX IF NOT EXISTS idx_diagnostic_content_audit_diagnostic_created
    ON diagnostic_content_audit(diagnostic_id, created_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM diagnostic_schema_migrations
         WHERE version='2026-08-25-kir-91-gameplay-v1'
    ) THEN
        -- No historical backfill. Existing completion_count remains authoritative for
        -- the legacy progress profile; new events begin at this migration boundary.
        INSERT INTO diagnostic_schema_migrations(version)
        VALUES ('2026-08-25-kir-91-gameplay-v1');
    END IF;
END $$;
"""
