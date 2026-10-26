"""Vercel serverless entry point for the FastAPI backend.

Vercel's Python runtime looks for an ASGI application named ``app`` in a file
under ``api/``. The application itself lives in ``backend/app`` so that the
same code runs unchanged under uvicorn locally, in Docker, and here -- this
module only puts it on the import path.

``vercel.json`` rewrites every ``/api/*`` request to this function and serves
the built React app for everything else, so the browser talks to a single
origin in production exactly as it does behind nginx in Docker.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402  (path set up above)

__all__ = ["app"]
