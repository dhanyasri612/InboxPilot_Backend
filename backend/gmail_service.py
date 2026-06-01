import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import gmail_client
from backend.categorization import analyze_emails
from backend.repository import save_emails_for_user, save_fetch_meta
from backend.services import normalize_email


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

    messages = gmail_client.list_message_ids(service, range_config["query"])
    emails_data = []

    for message in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message["id"])
            .execute()
        )

        payload = msg["payload"]
        headers = payload["headers"]

        subject = "No Subject"
        sender = "Unknown"

        for header in headers:
            if header["name"] == "Subject":
                subject = header["value"]
            elif header["name"] == "From":
                sender = header["value"]

        emails_data.append(
            {
                "id": message["id"],
                "subject": subject,
                "sender": sender,
                "body": gmail_client.extract_body(payload),
                "internalDate": msg.get("internalDate"),
                "ownerEmail": profile_email or requested_email,
            }
        )

    categorized = analyze_emails(emails_data, debug=False)
    owner = profile_email or requested_email
    save_emails_for_user(owner, categorized)

    meta = {
        "range": range_key,
        "rangeLabel": range_config["label"],
        "count": len(emails_data),
        "emailAddress": owner,
    }
    save_fetch_meta(owner, meta)

    return meta
