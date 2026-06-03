from sqlalchemy.orm import Session

from models import CAREER_CATEGORIES, Email, FetchMeta


def get_emails(db: Session, user_email: str, skip: int = 0, limit: int = 10000):
    return (
        db.query(Email)
        .filter(Email.user_email == user_email, _active_email_filters())
        .order_by(Email.priority.desc(), Email.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def _active_email_filters():
    return (Email.is_deleted.is_(False)) | (Email.is_deleted.is_(None))


def get_category_emails(
    db: Session,
    user_email: str,
    category: str,
    skip: int = 0,
    limit: int = 10000,
):
    return (
        db.query(Email)
        .filter(
            Email.user_email == user_email,
            Email.category == category,
            _active_email_filters(),
        )
        .order_by(Email.priority.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_career_emails(db: Session, user_email: str, skip: int = 0, limit: int = 10000):
    return (
        db.query(Email)
        .filter(
            Email.user_email == user_email,
            Email.career_related.is_(True),
            _active_email_filters(),
        )
        .order_by(Email.priority.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_email_by_gmail_id(db: Session, user_email: str, gmail_id: str):
    return (
        db.query(Email)
        .filter(Email.user_email == user_email, Email.gmail_id == gmail_id)
        .first()
    )


def delete_email(db: Session, gmail_id: str, user_email: str | None = None):
    query = db.query(Email).filter(Email.gmail_id == gmail_id)
    if user_email:
        query = query.filter(Email.user_email == user_email)
    record = query.first()
    if not record:
        return None
    record.is_deleted = True
    db.commit()
    return record


def delete_emails_by_gmail_ids(db: Session, user_email: str, gmail_ids: set[str]):
    if not gmail_ids:
        return 0
    updated = (
        db.query(Email)
        .filter(Email.user_email == user_email, Email.gmail_id.in_(gmail_ids))
        .update({Email.is_deleted: True}, synchronize_session=False)
    )
    db.commit()
    return updated


def replace_user_emails(db: Session, user_email: str, items: list[dict]):
    # Get all gmail_ids in the items list to query database for existing entries
    gmail_ids = [
        item.get("id") or item.get("gmail_id")
        for item in items
        if item.get("id") or item.get("gmail_id")
    ]
    
    existing = {}
    if gmail_ids:
        existing = {
            row.gmail_id: row
            for row in db.query(Email)
            .filter(Email.user_email == user_email, Email.gmail_id.in_(gmail_ids))
            .all()
        }

    for item in items:
        gmail_id = item.get("id") or item.get("gmail_id")
        if not gmail_id:
            continue

        category = item.get("category") or "Other"
        deadline_detected = bool(item.get("deadlineDetected") or item.get("deadline"))
        career_related = bool(item.get("career_related") or category in CAREER_CATEGORIES)
        confidence = int(item.get("confidence") or 0)
        priority = int(item.get("priority") or 20)
        ai_confidence = int(item.get("ai_confidence") or 0)
        internal_date = _parse_internal_date(item.get("internalDate"))

        if gmail_id in existing:
            email_row = existing[gmail_id]
            email_row.subject = item.get("subject") or ""
            email_row.sender = item.get("sender") or ""
            email_row.body = item.get("body") or ""
            email_row.company = item.get("company") or "Unknown"
            email_row.category = category
            email_row.subcategory = item.get("subcategory") or ""
            email_row.confidence = confidence
            email_row.priority = priority
            email_row.deadline = item.get("deadline")
            email_row.deadline_detected = deadline_detected
            email_row.career_related = career_related
            email_row.ai_category = item.get("ai_category") or "Other"
            email_row.ai_confidence = ai_confidence
            email_row.ai_reason = item.get("ai_reason") or ""
            email_row.validation_result = item.get("validation_result") or {}
            email_row.summary = item.get("summary") or ""
            email_row.internal_date = internal_date
            email_row.is_deleted = False
        else:
            db.add(
                Email(
                    user_email=user_email,
                    gmail_id=gmail_id,
                    subject=item.get("subject") or "",
                    sender=item.get("sender") or "",
                    body=item.get("body") or "",
                    company=item.get("company") or "Unknown",
                    category=category,
                    subcategory=item.get("subcategory") or "",
                    confidence=confidence,
                    priority=priority,
                    deadline=item.get("deadline"),
                    deadline_detected=deadline_detected,
                    career_related=career_related,
                    ai_category=item.get("ai_category") or "Other",
                    ai_confidence=ai_confidence,
                    ai_reason=item.get("ai_reason") or "",
                    validation_result=item.get("validation_result") or {},
                    summary=item.get("summary") or "",
                    internal_date=internal_date,
                    is_deleted=False,
                    application_status=item.get("applicationStatus") or "Discovered",
                )
            )

    db.commit()


def upsert_fetch_meta(db: Session, user_email: str, meta: dict):
    record = db.get(FetchMeta, user_email)
    if record is None:
        record = FetchMeta(user_email=user_email)
        db.add(record)

    record.range_key = meta.get("range") or meta.get("range_key") or "all"
    record.range_label = meta.get("rangeLabel") or meta.get("range_label") or ""
    record.count = int(meta.get("count") or 0)
    record.email_address = meta.get("emailAddress") or meta.get("email_address") or user_email
    db.commit()
    return record


def get_fetch_meta(db: Session, user_email: str):
    record = db.get(FetchMeta, user_email)
    return record.to_api_dict() if record else None


def _parse_internal_date(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def update_email_status(db: Session, user_email: str, gmail_id: str, status: str):
    record = db.query(Email).filter(Email.user_email == user_email, Email.gmail_id == gmail_id).first()
    if record:
        record.application_status = status
        db.commit()
    return record
