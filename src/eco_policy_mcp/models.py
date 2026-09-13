"""Shared response models: every tool result carries provenance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class Provenance(BaseModel):
    """Where a value came from and how fresh it is.

    Every successful tool response embeds this so downstream AI agents can
    cite the source instead of hallucinating.
    """

    source: str = Field(description="Human-readable source, e.g. 'AMFI NAVAll.txt'")
    as_of: datetime = Field(description="Data timestamp (UTC) when this was produced/fetched")
    reference: str | None = Field(default=None, description="Upstream URL or regulatory reference")
    note: str | None = Field(default=None, description="Caveats the caller should know")


def envelope(
    data: Any,
    *,
    source: str,
    reference: str | None = None,
    note: str | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Wrap `data` in the standard {data, provenance} envelope."""
    return {
        "data": data,
        "provenance": Provenance(
            source=source,
            as_of=as_of or utcnow(),
            reference=reference,
            note=note,
        ).model_dump(mode="json"),
    }
