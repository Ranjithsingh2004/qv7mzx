"""Domain-level exceptions mapped to HTTP responses in main.py."""

from __future__ import annotations


class AppError(Exception):
    """Base class for errors that carry a sensible HTTP status."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(AppError):
    """The caller supplied parameters that cannot produce an analysis."""

    status_code = 422
    code = "invalid_request"


class UpstreamError(AppError):
    """Elexon could not be reached, or returned something unusable."""

    status_code = 502
    code = "upstream_unavailable"
