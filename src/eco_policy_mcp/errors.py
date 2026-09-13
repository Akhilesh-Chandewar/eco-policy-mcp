"""Typed error hierarchy with a machine-readable wire format.

Tools NEVER raise raw exceptions at MCP clients: they catch EcoPolicyError
subclasses and return a structured {"error": {...}} payload so agents can
react programmatically (retry later, fix input, report no-data).
"""

from __future__ import annotations

from typing import Any


class EcoPolicyError(Exception):
    """Base class for all errors produced by this server."""

    code: str = "internal_error"
    http_hint: int | None = None

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint:
            err["hint"] = self.hint
        if self.details:
            err["details"] = self.details
        return {"error": err}


class ValidationError(EcoPolicyError):
    """Caller supplied bad input (negative amount, unknown regime, ...)."""

    code = "invalid_input"


class DataNotAvailableError(EcoPolicyError):
    """The source answered but has no data for this request."""

    code = "data_not_available"


class UpstreamUnavailableError(EcoPolicyError):
    """The upstream source is unreachable, blocked or failing."""

    code = "upstream_unavailable"


class RateLimitedError(UpstreamUnavailableError):
    """We are throttling ourselves to stay polite with the upstream."""

    code = "rate_limited"


def to_error_payload(exc: Exception) -> dict[str, Any]:
    """Convert any exception into the standard error envelope."""
    if isinstance(exc, EcoPolicyError):
        return exc.to_payload()
    return EcoPolicyError(
        f"Unexpected server error: {exc}", hint="This is likely a bug; please report it."
    ).to_payload()
