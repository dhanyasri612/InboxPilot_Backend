"""Lightweight schema patches for Supabase PostgreSQL."""

from sqlalchemy import text

from database import engine

_EMAIL_COLUMN_PATCHES = [
    "ALTER TABLE emails ADD COLUMN IF NOT EXISTS confidence BIGINT DEFAULT 0",
    "ALTER TABLE emails ADD COLUMN IF NOT EXISTS deadline_detected BOOLEAN DEFAULT FALSE",
    "ALTER TABLE emails ADD COLUMN IF NOT EXISTS career_related BOOLEAN DEFAULT FALSE",
    "ALTER TABLE emails ADD COLUMN IF NOT EXISTS ai_category TEXT DEFAULT 'Other'",
    "ALTER TABLE emails ADD COLUMN IF NOT EXISTS ai_confidence BIGINT DEFAULT 0",
    "ALTER TABLE emails ADD COLUMN IF NOT EXISTS ai_reason TEXT DEFAULT ''",
    "ALTER TABLE emails ADD COLUMN IF NOT EXISTS validation_result JSONB DEFAULT '{}'::jsonb",
    "ALTER TABLE emails ADD COLUMN IF NOT EXISTS internal_date BIGINT",
    "ALTER TABLE emails ADD COLUMN IF NOT EXISTS application_status TEXT DEFAULT 'Discovered'",
]


def run_schema_migrations():
    with engine.begin() as connection:
        for statement in _EMAIL_COLUMN_PATCHES:
            connection.execute(text(statement))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fetch_meta (
                    user_email VARCHAR(320) PRIMARY KEY,
                    range_key VARCHAR(32) NOT NULL,
                    range_label VARCHAR(128) DEFAULT '',
                    count INTEGER DEFAULT 0,
                    email_address VARCHAR(320) DEFAULT '',
                    fetched_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
