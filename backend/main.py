import logging
import os
import sys
from pathlib import Path

from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import gmail_client
from backend.gmail_service import fetch_and_save_for_user
from backend.repository import (
    delete_emails_for_user,
    get_email_by_gmail_id,
    init_database,
    update_email_status,
)
from backend.services import (
    build_daily_brief,
    build_dashboard_payload,
    filter_emails_by_range,
    get_deadline_emails,
    get_last_fetch_meta,
    load_emails_for_user,
    normalize_email,
)

logger = logging.getLogger("inboxpilot")
logging.basicConfig(level=logging.INFO)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

# Always allow production + local dev (never rely on FRONTEND_URL alone).
CORS_ALLOW_ORIGINS = [
    "https://inboxpilot-beta.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
]

# Preview deployments and other Vercel URLs (*.vercel.app).
CORS_ALLOW_ORIGIN_REGEX = r"https://([a-z0-9-]+\.)*vercel\.app"


def build_cors_origins() -> list[str]:
    origins = set(CORS_ALLOW_ORIGINS)
    if FRONTEND_URL:
        origins.add(FRONTEND_URL)
    for origin in os.getenv("CORS_ORIGINS", "").split(","):
        cleaned = origin.strip().rstrip("/")
        if cleaned:
            origins.add(cleaned)
    return sorted(origins)


CORS_ORIGINS = build_cors_origins()

app = FastAPI(title="InboxPilot API", version="1.0.0")

# Middleware must be registered before routes (Starlette runs last-added first).
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)


def log_registered_routes() -> None:
    logger.info("InboxPilot API module: backend.main:app")
    logger.info("CORS allow_origins: %s", ", ".join(CORS_ORIGINS))
    logger.info("CORS allow_origin_regex: %s", CORS_ALLOW_ORIGIN_REGEX)
    logger.info("FRONTEND_URL env: %s", FRONTEND_URL or "(not set)")
    logger.info("Registered routes:")
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if methods and path:
            method_list = sorted(methods - {"HEAD", "OPTIONS"})
            logger.info("  %-18s %s", ",".join(method_list), path)


@app.on_event("startup")
def on_startup():
    init_database()
    log_registered_routes()
    oauth = gmail_client.get_oauth_config()
    logger.info("Gmail OAuth redirect_uri: %s", oauth.get("redirectUri"))
    logger.info("Gmail OAuth client type: %s", oauth.get("clientType"))


class FetchRequest(BaseModel):
    email: EmailStr
    range: str = Field(default="today")


class DeleteRequest(BaseModel):
    messageId: str
    email: EmailStr | None = None


class BulkActionRequest(BaseModel):
    messageIds: list[str]
    action: str
    email: EmailStr | None = None


class RefreshRequest(BaseModel):
    email: EmailStr
    range: str = Field(default="all")


class UpdateStatusRequest(BaseModel):
    messageId: str
    status: str
    email: EmailStr | None = None


class GenerateReplyRequest(BaseModel):
    messageId: str
    replyType: str
    email: EmailStr | None = None


def require_email(email: str | None) -> str:
    if not email or "@" not in email:
        raise HTTPException(
            status_code=400,
            detail="Email is required. Add your Gmail address in Settings.",
        )
    return normalize_email(email)


def load_scoped_emails(email: str, range_key: str):
    emails = load_emails_for_user(email)
    return filter_emails_by_range(emails, range_key)


def _remove_emails_from_store(email: str | None, gmail_ids: set[str]):
    if not email or not gmail_ids:
        return
    delete_emails_for_user(normalize_email(email), gmail_ids)


def _gmail_profile_payload() -> dict:
    profile = gmail_client.get_gmail_profile()
    if not profile:
        return {
            "email": "",
            "emailAddress": "",
            "connected": False,
        }

    address = profile.get("emailAddress") or ""
    return {
        "email": address,
        "emailAddress": address,
        "connected": True,
        "messagesTotal": profile.get("messagesTotal"),
        "threadsTotal": profile.get("threadsTotal"),
    }


@app.get("/")
def root():
    return {
        "service": "InboxPilot API",
        "health": "/health",
        "gmailProfile": "/gmail/profile",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/gmail/status")
def gmail_status(email: str | None = Query(default=None)):
    has_token = gmail_client.TOKEN_PATH.is_file()
    has_credentials = gmail_client.credentials_configured()
    profile = None

    if has_token:
        try:
            profile = gmail_client.get_gmail_profile()
        except Exception:
            profile = None

    last_fetch = get_last_fetch_meta(normalize_email(email)) if email else None

    return {
        "oauthReady": has_token,
        "credentialsConfigured": has_credentials,
        "oauthRedirectUri": gmail_client.get_oauth_redirect_uri(),
        "oauthClientType": gmail_client.credentials_client_type(),
        "emailAddress": profile.get("emailAddress") if profile else None,
        "lastFetch": last_fetch,
        "message": (
            "Gmail API is ready."
            if has_token
            else "Connect Gmail from Settings to authorize API access."
        ),
    }


@app.get("/gmail/profile")
def gmail_profile():
    return _gmail_profile_payload()


@app.post("/gmail/disconnect")
def gmail_disconnect():
    gmail_client.disconnect_gmail()
    return {"success": True}


@app.get("/gmail/oauth/config")
def gmail_oauth_config():
    """Debug: exact redirect_uri sent to Google (no secrets)."""
    return gmail_client.get_oauth_config()


@app.get("/gmail/oauth/start")
def gmail_oauth_start(next: str | None = Query(default=None)):
    return_url = next or f"{FRONTEND_URL}/settings"

    try:
        session = gmail_client.start_web_oauth(next_url=return_url)
        return RedirectResponse(session["authUrl"], status_code=302)
    except (ValueError, FileNotFoundError) as error:
        message = quote(str(error))
        return RedirectResponse(
            f"{return_url}?gmail=error&message={message}",
            status_code=302,
        )
    except Exception as error:
        message = quote(f"OAuth start failed: {error}")
        return RedirectResponse(
            f"{return_url}?gmail=error&message={message}",
            status_code=302,
        )


@app.get("/gmail/oauth/callback")
def gmail_oauth_callback(request: Request, state: str = Query(default="")):
    try:
        result = gmail_client.complete_web_oauth(state, str(request.url))
        profile = result.get("profile") or {}
        next_url = result.get("next_url") or f"{FRONTEND_URL}/settings"
        return RedirectResponse(
            f"{next_url}?gmail=connected&email={profile.get('emailAddress', '')}",
            status_code=302,
        )
    except Exception as error:
        return RedirectResponse(
            f"{FRONTEND_URL}/settings?gmail=error&message={str(error)}",
            status_code=302,
        )


@app.get("/inbox/scope-options")
def inbox_scope_options():
    return {"options": gmail_client.get_fetch_options()}


@app.get("/dashboard")
def dashboard(
    email: str | None = Query(default=None),
    range: str = Query(default="all"),
):
    user_email = require_email(email)
    emails = load_scoped_emails(user_email, range)
    return build_dashboard_payload(emails)


@app.get("/emails")
def emails(
    email: str | None = Query(default=None),
    range: str = Query(default="all"),
):
    user_email = require_email(email)
    return load_scoped_emails(user_email, range)


@app.get("/daily-brief")
def daily_brief(
    email: str | None = Query(default=None),
    range: str = Query(default="all"),
):
    user_email = require_email(email)
    emails = load_scoped_emails(user_email, range)
    return build_daily_brief(emails)


@app.get("/deadlines")
def deadlines(
    email: str | None = Query(default=None),
    range: str = Query(default="all"),
):
    user_email = require_email(email)
    emails = load_scoped_emails(user_email, range)
    return {"items": get_deadline_emails(emails)}


@app.post("/gmail/fetch")
def gmail_fetch(payload: FetchRequest):
    if payload.range not in gmail_client.FETCH_RANGES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid range.",
                "validRanges": list(gmail_client.FETCH_RANGES.keys()),
            },
        )

    try:
        result = fetch_and_save_for_user(str(payload.email), payload.range)
        return {
            "success": True,
            "range": result["range"],
            "rangeLabel": result["rangeLabel"],
            "count": result["count"],
            "emailAddress": result.get("emailAddress"),
            "message": f"Fetched {result['count']} emails ({result['rangeLabel']}).",
        }
    except FileNotFoundError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch emails: {error}",
        ) from error


@app.post("/refresh")
def refresh_inbox(payload: RefreshRequest):
    try:
        result = fetch_and_save_for_user(str(payload.email), payload.range)
        return {
            "success": True,
            "count": result.get("count", 0),
            "range": result.get("range", payload.range),
            "rangeLabel": result.get("rangeLabel"),
            "message": "Inbox refreshed.",
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Refresh failed: {error}") from error


@app.post("/emails/update-status")
def update_email_application_status(payload: UpdateStatusRequest):
    user_email = require_email(payload.email)
    try:
        record = update_email_status(user_email, payload.messageId, payload.status)
        if not record:
            raise HTTPException(status_code=404, detail="Email not found.")
        return {"success": True, "messageId": payload.messageId, "status": payload.status}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Status update failed: {error}") from error


@app.post("/emails/generate-reply")
def generate_email_reply_draft(payload: GenerateReplyRequest):
    user_email = require_email(payload.email)
    try:
        record = get_email_by_gmail_id(user_email, payload.messageId)
        if not record:
            raise HTTPException(status_code=404, detail="Email not found.")
        
        from backend.groq_client import generate_reply_draft
        draft = generate_reply_draft(
            subject=record.subject,
            sender=record.sender,
            body=record.body,
            reply_type=payload.replyType,
        )
        return {"success": True, "draft": draft}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Draft generation failed: {error}") from error


@app.post("/emails/delete")
def delete_email(payload: DeleteRequest):
    service = gmail_client.get_gmail_service()
    if not service:
        raise HTTPException(status_code=401, detail="Gmail is not authorized.")

    try:
        service.users().messages().trash(userId="me", id=payload.messageId).execute()
        if payload.email:
            _remove_emails_from_store(str(payload.email), {payload.messageId})
        return {"success": True}
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Delete failed: {error}") from error


@app.post("/emails/bulk-action")
def bulk_email_action(payload: BulkActionRequest):
    if not payload.messageIds:
        return {"success": True, "processed": 0}

    service = gmail_client.get_gmail_service()
    if not service:
        raise HTTPException(status_code=401, detail="Gmail is not authorized.")

    action = payload.action.strip().lower()
    processed = 0
    failures = []

    for message_id in payload.messageIds:
        try:
            if action in {"delete", "trash"}:
                service.users().messages().trash(userId="me", id=message_id).execute()
            elif action == "archive":
                service.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={"removeLabelIds": ["INBOX"]},
                ).execute()
            elif action == "mark_read":
                service.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={"removeLabelIds": ["UNREAD"]},
                ).execute()
            elif action == "mark_important":
                service.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={"addLabelIds": ["IMPORTANT"]},
                ).execute()
            else:
                raise ValueError(f"Unsupported action: {payload.action}")

            processed += 1
        except Exception as error:
            failures.append({"id": message_id, "error": str(error)})

    if action in {"delete", "trash", "archive"} and payload.email:
        remove_ids = set(payload.messageIds)
        _remove_emails_from_store(str(payload.email), remove_ids)

    return {
        "success": len(failures) == 0,
        "processed": processed,
        "failed": failures,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
