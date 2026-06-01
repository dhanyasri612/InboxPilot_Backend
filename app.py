"""InboxPilot API entrypoint — delegates to the full FastAPI app in backend/main.py.

Run:
    uvicorn app:app --reload --host 0.0.0.0 --port 8000
    # or
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""

from backend.main import app

__all__ = ["app"]
