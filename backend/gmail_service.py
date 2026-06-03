import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import gmail_client
from backend.categorization import analyze_emails
from backend.repository import save_emails_for_user, save_fetch_meta
from backend.services import normalize_email
from database import SessionLocal
from models import Email


def fetch_and_save_for_user(email: str, range_key: str):
    range_config = gmail_client.get_range_config(range_key)
    if not range_config:
        raise ValueError(f"Unknown fetch range: {range_key}")

    service = gmail_client.get_gmail_service()
    if not service:
        raise RuntimeError(
            "Gmail API is not authorized. Run read_emails.py once to create token.json."
        )

    profile = service.users().getProfile(userId="me").execute()
    profile_email = normalize_email(profile.get("emailAddress", ""))
    requested_email = normalize_email(email)

    if profile_email and requested_email and profile_email != requested_email:
        raise RuntimeError(
            f"Gmail token belongs to {profile_email}, not {requested_email}."
        )

    owner = profile_email or requested_email

    # Fetch message IDs from Gmail
    messages = gmail_client.list_message_ids(service, range_config["query"])
    # Cap total messages to 200 for sync performance
    messages = messages
    gmail_ids = [m["id"] for m in messages]

    # Check database to see which ones are already present
    existing_map = {}
    if gmail_ids:
        db = SessionLocal()
        try:
            existing_rows = (
                db.query(Email)
                .filter(Email.user_email == owner, Email.gmail_id.in_(gmail_ids))
                .all()
            )
            existing_map = {row.gmail_id: row.to_api_dict() for row in existing_rows}
        finally:
            db.close()

    # Find which ones need to be fetched
    to_fetch_ids = [mid for mid in gmail_ids if mid not in existing_map]
    fetched_emails = []

    if to_fetch_ids:
        # Fetch email details in parallel using ThreadPoolExecutor
        def fetch_msg_details(msg_id):
            thread_service = gmail_client.get_gmail_service()
            if not thread_service:
                return None
            try:
                msg = (
                    thread_service.users()
                    .messages()
                    .get(userId="me", id=msg_id)
                    .execute()
                )
                payload = msg.get("payload", {})
                headers = payload.get("headers", [])

                subject = "No Subject"
                sender = "Unknown"

                for header in headers:
                    if header["name"] == "Subject":
                        subject = header["value"]
                    elif header["name"] == "From":
                        sender = header["value"]

                # Extract and clean raw body immediately
                raw_body = gmail_client.extract_body(payload)
                cleaned_body = gmail_client.clean_html_to_plain_text(raw_body)

                return {
                    "id": msg_id,
                    "subject": subject,
                    "sender": sender,
                    "body": cleaned_body,
                    "internalDate": msg.get("internalDate"),
                    "ownerEmail": owner,
                }
            except Exception as e:
                print(f"Error fetching message {msg_id}: {e}")
                return None

        # Fetch in parallel with 10 worker threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_msg_details, mid) for mid in to_fetch_ids]
            for fut in futures:
                res = fut.result()
                if res:
                    fetched_emails.append(res)

    # Analyze only the newly fetched emails
    new_categorized = []
    if fetched_emails:
        new_categorized = analyze_emails(fetched_emails, debug=False)

    new_categorized_map = {item["id"]: item for item in new_categorized}

    # Reconstruct the combined list of categorized emails matching the original fetch order
    all_categorized = []
    for mid in gmail_ids:
        if mid in existing_map:
            all_categorized.append(existing_map[mid])
        elif mid in new_categorized_map:
            all_categorized.append(new_categorized_map[mid])

    # Save to the database
    save_emails_for_user(owner, all_categorized)

    meta = {
        "range": range_key,
        "rangeLabel": range_config["label"],
        "count": len(all_categorized),
        "emailAddress": owner,
    }
    save_fetch_meta(owner, meta)

    return meta
