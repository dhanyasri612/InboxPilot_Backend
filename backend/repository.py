import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import crud
from database import SessionLocal
from backend.schema_migrations import run_schema_migrations
from database import engine

from backend.services import (
    load_json_file,
    normalize_email,
    user_emails_path,
    user_fetch_meta_path,
    user_results_path,
)


def init_database():
    run_schema_migrations()


def _with_db(action):
    db = SessionLocal()
    try:
        return action(db)
    finally:
        db.close()


def load_emails_for_user(email: str) -> list[dict]:
    normalized = normalize_email(email)
    if not normalized:
        return []

    emails = _with_db(lambda db: crud.get_emails(db, normalized))
    if emails:
        return [row.to_api_dict() for row in emails]

    migrated = _migrate_json_store_if_present(normalized)
    return migrated


def save_emails_for_user(email: str, items: list[dict]):
    normalized = normalize_email(email)
    if not normalized:
        return

    _with_db(lambda db: crud.replace_user_emails(db, normalized, items))


def delete_emails_for_user(email: str, gmail_ids: set[str]):
    normalized = normalize_email(email)
    if not normalized or not gmail_ids:
        return

    _with_db(lambda db: crud.delete_emails_by_gmail_ids(db, normalized, gmail_ids))


def update_email_status(email: str, gmail_id: str, status: str):
    normalized = normalize_email(email)
    if not normalized:
        return None
    return _with_db(lambda db: crud.update_email_status(db, normalized, gmail_id, status))


def get_email_by_gmail_id(email: str, gmail_id: str):
    normalized = normalize_email(email)
    if not normalized:
        return None
    return _with_db(lambda db: crud.get_email_by_gmail_id(db, normalized, gmail_id))


def get_last_fetch_meta(email: str):
    normalized = normalize_email(email)
    if not normalized:
        return None

    meta = _with_db(lambda db: crud.get_fetch_meta(db, normalized))
    if meta:
        return meta

    path = user_fetch_meta_path(normalized)
    legacy = load_json_file(path, None)
    if legacy:
        _with_db(lambda db: crud.upsert_fetch_meta(db, normalized, legacy))
    return legacy


def save_fetch_meta(email: str, meta: dict):
    normalized = normalize_email(email)
    if not normalized:
        return

    _with_db(lambda db: crud.upsert_fetch_meta(db, normalized, meta))


def _migrate_json_store_if_present(email: str) -> list[dict]:
    results_path = user_results_path(email)
    emails_path = user_emails_path(email)
    records = load_json_file(results_path, [])
    if not records:
        records = load_json_file(emails_path, [])

    if not isinstance(records, list) or not records:
        return []

    _with_db(lambda db: crud.replace_user_emails(db, email, records))

    meta_path = user_fetch_meta_path(email)
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(meta, dict):
                _with_db(lambda db: crud.upsert_fetch_meta(db, email, meta))
        except json.JSONDecodeError:
            pass

    return records
