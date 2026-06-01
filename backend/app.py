"""Legacy Flask entrypoint. Use FastAPI instead:

    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""

raise SystemExit(
    "Flask backend removed. Start FastAPI with:\n"
    "  uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000"
)
