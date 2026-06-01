import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

RANGE_DAYS = {"today": 1, "7d": 7, "30d": 30}


def normalize_category(category: str | None) -> str:
    if not category:
        return "Other"

    normalized = category.strip().lower()
    aliases = {
        "ai tools": "AI Tools",
        "product updates": "Product Updates",
        "notifications": "Notifications",
        "jobs": "Job",
        "job": "Job",
        "internships": "Internship",
        "internship": "Internship",
        "interviews": "Interview",
        "interview": "Interview",
        "promotions": "Promotion",
        "promotion": "Promotion",
        "newsletters": "Newsletter",
        "newsletter": "Newsletter",
        "learning": "Learning",
        "security": "Security",
        "account": "Account",
        "spam": "Spam",
        "networking": "Networking",
        "college": "College",
        "social": "Social",
        "finance": "Finance",
        "shopping": "Shopping",
        "travel": "Travel",
        "events": "Events",
        "support": "Support",
        "health": "Health",
        "entertainment": "Entertainment",
    }
    return aliases.get(normalized, category.strip())


def normalize_email(email: str) -> str:
    return email.strip().lower()


def user_data_dir(email: str) -> Path:
    safe = re.sub(r"[^a-z0-9._-]", "_", normalize_email(email))
    path = ROOT_DIR / "data" / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_emails_path(email: str) -> Path:
    return user_data_dir(email) / "emails.json"


def user_results_path(email: str) -> Path:
    return user_data_dir(email) / "results.json"


def user_fetch_meta_path(email: str) -> Path:
    return user_data_dir(email) / "fetch_meta.json"


def load_json_file(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
            return data if data is not None else default
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def load_emails_for_user(email: str):
    from backend.repository import load_emails_for_user as load_from_db

    return load_from_db(email)


def filter_emails_by_range(emails, range_key):
    if not range_key or range_key == "all":
        return emails

    days = RANGE_DAYS.get(range_key)
    if not days:
        return emails

    dated_emails = [email for email in emails if email.get("internalDate")]
    if not dated_emails:
        return emails

    cutoff_ms = int(
        (datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000
    )

    return [
        email
        for email in emails
        if email.get("internalDate") and int(email["internalDate"]) >= cutoff_ms
    ]


def build_dashboard_payload(emails):
    category_counter = Counter()
    company_counter = Counter()
    jobs = 0
    internships = 0
    interviews = 0
    promotions = 0
    spam = 0
    security_alerts = 0
    newsletters = 0
    learning = 0
    deadlines = 0

    for email in emails:
        category = normalize_category(email.get("category") or "Other")
        category_counter[category] += 1
        company = (email.get("company") or "Unknown").strip() or "Unknown"
        if company != "Unknown":
            company_counter[company] += 1

        lowered = category.lower()
        if lowered == "job":
            jobs += 1
        elif lowered == "internship":
            internships += 1
        elif lowered == "interview":
            interviews += 1
        elif lowered == "promotion":
            promotions += 1
        elif lowered == "spam":
            spam += 1
        elif lowered == "security":
            security_alerts += 1
        elif lowered == "newsletter":
            newsletters += 1
        elif lowered == "learning":
            learning += 1

        if email.get("deadline") or email.get("deadlineDetected"):
            deadlines += 1
            email["deadlineDetected"] = True
        else:
            email["deadlineDetected"] = False

    return {
        "totalEmails": len(emails),
        "jobs": jobs,
        "internships": internships,
        "interviews": interviews,
        "promotions": promotions,
        "newsletters": newsletters,
        "learning": learning,
        "securityAlerts": security_alerts,
        "spam": spam,
        "deadlines": deadlines,
        "categoryCounts": dict(category_counter),
        "topCompanies": company_counter.most_common(10),
        "careerEmails": sum(1 for email in emails if email.get("career_related")),
    }


def build_daily_brief(emails):
    dashboard = build_dashboard_payload(emails)
    sorted_emails = sorted(
        emails, key=lambda item: item.get("priority", 0), reverse=True
    )
    top_email = sorted_emails[0] if sorted_emails else None

    lines = ["Inbox Summary", ""]
    lines.append(f"- {dashboard['jobs']} Job Opportunities")
    lines.append(f"- {dashboard['internships']} Internships")
    lines.append(f"- {dashboard['interviews']} Interviews")
    lines.append(
        f"- {dashboard['learning']} Learning Emails"
    )
    lines.append(f"- {dashboard['promotions']} Promotions")
    lines.append(f"- {dashboard['newsletters']} Newsletters")
    lines.append(f"- {dashboard['securityAlerts']} Security Alerts")
    lines.append("")
    lines.append("Top Opportunity:")
    lines.append(
        top_email["subject"] if top_email else "No high-priority opportunity detected"
    )

    return {"brief": "\n".join(lines)}


def get_last_fetch_meta(email: str):
    from backend.repository import get_last_fetch_meta as load_meta_from_db

    return load_meta_from_db(email)


def deadline_sort_key(email):
    value = (email.get("deadline") or "").strip().lower()
    if not value:
        return (9999, "")

    special = {
        "today": 0,
        "tomorrow": 1,
        "this week": 3,
        "next week": 7,
    }

    for key, rank in special.items():
        if key in value:
            return (rank, value)

    date_match = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", value)
    if date_match:
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        year = int(date_match.group(3) or datetime.now(timezone.utc).year)
        if year < 100:
            year += 2000
        try:
            dt = datetime(year, month, day, tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta_days = max((dt - now).days, 0)
            return (delta_days, value)
        except ValueError:
            pass

    month_names = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    month_match = re.search(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:,\s*(\d{4}))?",
        value,
    )
    if month_match:
        month = month_names[month_match.group(1)]
        day = int(month_match.group(2))
        year = int(month_match.group(3) or datetime.now(timezone.utc).year)
        try:
            dt = datetime(year, month, day, tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta_days = max((dt - now).days, 0)
            return (delta_days, value)
        except ValueError:
            pass

    return (3650, value)


def get_deadline_emails(emails):
    with_deadline = []
    for email in emails:
        deadline = email.get("deadline")
        if deadline:
            enriched = dict(email)
            enriched["deadlineDetected"] = True
            with_deadline.append(enriched)
    return sorted(with_deadline, key=deadline_sort_key)
