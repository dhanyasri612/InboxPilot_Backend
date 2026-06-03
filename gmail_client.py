import base64
import html
import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()

logger = logging.getLogger("inboxpilot.gmail")

ROOT_DIR = Path(__file__).resolve().parent
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_PATH = ROOT_DIR / "token.json"
CREDENTIALS_PATH = ROOT_DIR / "credentials.json"
EMAILS_PATH = ROOT_DIR / "emails.json"
FETCH_META_PATH = ROOT_DIR / "fetch_meta.json"

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def resolve_oauth_redirect_uri() -> str:
    """
    Redirect URI sent to Google in the OAuth authorization request.

    Priority:
    1. GMAIL_OAUTH_REDIRECT_URI (explicit)
    2. RENDER_EXTERNAL_URL + /gmail/oauth/callback (Render auto URL)
    3. localhost default for dev
    """
    explicit = (os.getenv("GMAIL_OAUTH_REDIRECT_URI") or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/gmail/oauth/callback" if not explicit.endswith(
            "/gmail/oauth/callback"
        ) else explicit

    render_host = (os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if render_host:
        return f"{render_host}/gmail/oauth/callback"

    return "http://localhost:8000/gmail/oauth/callback"


def get_oauth_redirect_uri() -> str:
    """Current redirect URI (re-read env each call for tests and hot config)."""
    return resolve_oauth_redirect_uri()


def _enable_local_insecure_transport_if_needed():
    """Allow OAuth over http only for local development callbacks."""
    uri = get_oauth_redirect_uri().lower()
    if uri.startswith("http://localhost") or uri.startswith("http://127.0.0.1"):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

FETCH_RANGES = {
    "today": {
        "id": "today",
        "label": "Today's Emails",
        "description": "Messages from the last 24 hours",
        "query": "newer_than:1d",
    },
    "7d": {
        "id": "7d",
        "label": "Last 7 Days",
        "description": "Messages from the past week",
        "query": "newer_than:7d",
    },
    "30d": {
        "id": "30d",
        "label": "Last 30 Days",
        "description": "Messages from the past month",
        "query": "newer_than:30d",
    },
    "all": {
        "id": "all",
        "label": "All Emails",
        "description": "Full inbox (may take longer)",
        "query": None,
    },
}

_oauth_states = {}


def _credentials_json_from_env() -> str | None:
    raw = (os.getenv("GMAIL_CREDENTIALS_JSON") or "").strip()
    return raw or None


def ensure_credentials_file() -> bool:
    """
    Make credentials.json available for OAuth.

    On Render, set GMAIL_CREDENTIALS_JSON. When that env var is present it always
    wins over an existing credentials.json (fixes stale Secret File / old deploy).
    """
    raw = _credentials_json_from_env()

    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError("GMAIL_CREDENTIALS_JSON is not valid JSON") from error

        serialized = json.dumps(parsed)
        if CREDENTIALS_PATH.is_file():
            try:
                if CREDENTIALS_PATH.read_text(encoding="utf-8") == serialized:
                    return True
            except OSError:
                pass

        CREDENTIALS_PATH.write_text(serialized, encoding="utf-8")
        return True

    if CREDENTIALS_PATH.is_file():
        return True

    return False


def credentials_configured() -> bool:
    return CREDENTIALS_PATH.is_file() or bool(_credentials_json_from_env())


def _require_credentials_file():
    if not ensure_credentials_file():
        raise FileNotFoundError(
            "Gmail OAuth credentials are not configured. "
            "Add credentials.json on the server or set GMAIL_CREDENTIALS_JSON."
        )


def credentials_client_type() -> str | None:
    if not CREDENTIALS_PATH.is_file() and not _credentials_json_from_env():
        return None
    ensure_credentials_file()
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if "web" in data:
        return "web"
    if "installed" in data:
        return "installed"
    return "unknown"


def _create_oauth_flow(redirect_uri: str) -> Flow:
    """Build OAuth flow from web credentials, or adapt installed creds for local dev only."""
    _require_credentials_file()
    data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))

    if "web" in data:
        return Flow.from_client_secrets_file(
            str(CREDENTIALS_PATH),
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )

    if "installed" in data:
        is_local = redirect_uri.startswith("http://localhost") or redirect_uri.startswith(
            "http://127.0.0.1"
        )
        if not is_local:
            raise ValueError(
                "Gmail OAuth credentials are type 'installed' (Desktop). "
                "Production requires a Google Cloud OAuth client of type 'Web application' "
                f"with redirect URI: {redirect_uri}. "
                "Create a Web client, download JSON, and set GMAIL_CREDENTIALS_JSON on Render."
            )

        installed = data["installed"]
        web_config = {
            "web": {
                "client_id": installed["client_id"],
                "client_secret": installed["client_secret"],
                "auth_uri": installed["auth_uri"],
                "token_uri": installed["token_uri"],
                "redirect_uris": [redirect_uri],
            }
        }
        return Flow.from_client_config(
            web_config,
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )

    raise ValueError("Invalid OAuth credentials: expected 'web' or 'installed' section.")


def get_oauth_config() -> dict:
    redirect_uri = get_oauth_redirect_uri()
    return {
        "redirectUri": redirect_uri,
        "clientType": credentials_client_type(),
        "credentialsConfigured": credentials_configured(),
        "frontendUrl": FRONTEND_URL,
        "isLocalRedirect": redirect_uri.startswith("http://localhost")
        or redirect_uri.startswith("http://127.0.0.1"),
    }


def get_fetch_options():
    return list(FETCH_RANGES.values())


def get_range_config(range_key):
    return FETCH_RANGES.get(range_key)


def clean_html_to_plain_text(html_str: str) -> str:
    if not html_str:
        return ""
    # Strip script tags and content
    text = re.sub(r"<script[^>]*?>.*?</script>", " ", html_str, flags=re.DOTALL | re.IGNORECASE)
    # Strip style tags and content
    text = re.sub(r"<style[^>]*?>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    # Strip other HTML tags
    text = re.sub(r"<[^>]*>", " ", text)
    # Decode HTML entities
    text = html.unescape(text)
    # Normalize spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_body(payload):
    def find_part(parts, mime_type):
        for part in parts:
            if part.get("mimeType") == mime_type:
                data = part.get("body", {}).get("data")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            if "parts" in part:
                res = find_part(part["parts"], mime_type)
                if res:
                    return res
        return None

    try:
        # 1. Try to find text/plain anywhere in nested parts
        if "parts" in payload:
            plain_text = find_part(payload["parts"], "text/plain")
            if plain_text:
                return plain_text
            
            # 2. Try to find text/html if text/plain is missing
            html_text = find_part(payload["parts"], "text/html")
            if html_text:
                return clean_html_to_plain_text(html_text)

        # 3. Fallback to main payload body
        mime = payload.get("mimeType", "")
        data = payload.get("body", {}).get("data")
        if data:
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            if mime == "text/html":
                return clean_html_to_plain_text(decoded)
            return decoded
    except Exception:
        pass

    return ""


def load_credentials():
    creds = None

    if TOKEN_PATH.is_file():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_credentials(creds)
        else:
            return None

    return creds


def save_credentials(creds):
    with TOKEN_PATH.open("w", encoding="utf-8") as token_file:
        token_file.write(creds.to_json())


def clear_credentials():
    if TOKEN_PATH.is_file():
        TOKEN_PATH.unlink()


def clear_oauth_sessions():
    _oauth_states.clear()


def get_gmail_service():
    creds = load_credentials()
    if not creds:
        return None

    return build("gmail", "v1", credentials=creds)


def get_gmail_profile():
    service = get_gmail_service()
    if not service:
        return None

    profile = service.users().getProfile(userId="me").execute()
    return {
        "emailAddress": profile.get("emailAddress"),
        "messagesTotal": profile.get("messagesTotal"),
        "threadsTotal": profile.get("threadsTotal"),
    }


def list_message_ids(service, query):
    all_messages = []
    page_token = None

    while True:
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=500,
                pageToken=page_token,
            )
            .execute()
        )

        all_messages.extend(response.get("messages", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return all_messages


def get_last_fetch_meta():
    return json.loads(FETCH_META_PATH.read_text(encoding="utf-8")) if FETCH_META_PATH.is_file() else None


def run_cli_oauth():
    _require_credentials_file()

    _enable_local_insecure_transport_if_needed()
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0, prompt="select_account consent")
    save_credentials(creds)
    return creds


def start_web_oauth(next_url=None):
    redirect_uri = get_oauth_redirect_uri()
    logger.info("Starting Gmail web OAuth with redirect_uri=%s", redirect_uri)

    _enable_local_insecure_transport_if_needed()

    flow = _create_oauth_flow(redirect_uri)

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account consent",
    )

    logger.info("Google authorization URL redirect_uri param: %s", redirect_uri)

    _oauth_states[state] = {"flow": flow, "next_url": next_url}
    return {"authUrl": authorization_url, "state": state, "redirectUri": redirect_uri}


def complete_web_oauth(state, authorization_response):
    session = _oauth_states.pop(state, None)
    if not session:
        raise RuntimeError("OAuth session expired. Start authorization again.")

    flow = session["flow"]

    flow.fetch_token(authorization_response=authorization_response)
    save_credentials(flow.credentials)
    profile = get_gmail_profile()
    return {"profile": profile or {}, "next_url": session.get("next_url")}


def disconnect_gmail():
    clear_oauth_sessions()
    clear_credentials()
    return {"success": True}