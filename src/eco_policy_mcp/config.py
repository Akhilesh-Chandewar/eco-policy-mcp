"""Runtime configuration, overridable via environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        return float(raw) if raw is not None else default
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """All knobs in one place. Env prefix: ECO_"""

    user_agent: str = field(
        default_factory=lambda: os.getenv(
            "ECO_USER_AGENT",
            "eco-policy-mcp/0.1 (+https://github.com/eco-policy-mcp/eco-policy-mcp)",
        )
    )

    # --- upstream URLs -----------------------------------------------------
    amfi_nav_url: str = field(
        default_factory=lambda: os.getenv(
            "ECO_AMFI_NAV_URL", "https://www.amfiindia.com/spages/NAVAll.txt"
        )
    )
    mfapi_base: str = field(
        default_factory=lambda: os.getenv("ECO_MFAPI_BASE", "https://api.mfapi.in")
    )
    nse_base: str = field(
        default_factory=lambda: os.getenv("ECO_NSE_BASE", "https://www.nseindia.com")
    )

    # --- HTTP behaviour ----------------------------------------------------
    http_timeout_seconds: float = field(
        default_factory=lambda: _env_float("ECO_HTTP_TIMEOUT", 15.0)
    )
    nse_timeout_seconds: float = field(
        default_factory=lambda: _env_float("ECO_NSE_TIMEOUT", 10.0)
    )
    nse_min_interval_seconds: float = field(
        default_factory=lambda: _env_float("ECO_NSE_MIN_INTERVAL", 0.6)
    )

    # --- cache TTLs (seconds) ----------------------------------------------
    ttl_amfi_index: float = field(
        default_factory=lambda: _env_float("ECO_TTL_AMFI_INDEX", 6 * 3600)
    )
    ttl_nav_history: float = field(
        default_factory=lambda: _env_float("ECO_TTL_NAV_HISTORY", 12 * 3600)
    )
    ttl_nse_quote: float = field(
        default_factory=lambda: _env_float("ECO_TTL_NSE_QUOTE", 60.0)
    )

    # --- misc --------------------------------------------------------------
    max_search_results: int = field(
        default_factory=lambda: _env_int("ECO_MAX_SEARCH_RESULTS", 50)
    )


settings = Settings()
