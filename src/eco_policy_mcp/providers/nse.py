"""NSE market-data provider (unofficial public endpoints).

NSE serves browser clients; their API endpoints require a session cookie
obtained by first visiting nseindia.com. This module:

1. performs a lightweight handshake and keeps the cookie jar warm,
2. self-throttles (>= ECO_NSE_MIN_INTERVAL between upstream calls),
3. never forwards raw HTML to AI clients - on any block/failure it returns
   the standard structured error payload so agents can react gracefully.

Endpoints used (public, undocumented):
- /api/quote-equity?symbol=INFY
- /api/equity-stockIndices?index=NIFTY 50
- /api/historical/cm/equity?symbol=INFY&from=..&to=..
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import date, timedelta

from ..cache import nse_cache
from ..config import settings
from ..errors import DataNotAvailableError, UpstreamUnavailableError
from ..models import envelope
from .http import get_client

NSE_SOURCE = "NSE India public API (unofficial)"
NSE_REF = "https://www.nseindia.com"

_last_call_ts = 0.0
_throttle_lock = asyncio.Lock()


async def _throttle() -> None:
    global _last_call_ts
    async with _throttle_lock:
        wait = settings.nse_min_interval_seconds - (time.monotonic() - _last_call_ts)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_ts = time.monotonic()


async def _nse_get_json(path: str, params: dict | None = None) -> dict:
    """GET an NSE API path, handling session cookie handshake and errors."""
    client = get_client()

    # --- handshake: prime cookies by touching the homepage -------------------
    try:
        await client.get(
            settings.nse_base,
            headers={
                "Accept": "text/html",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": settings.nse_base,
            },
        )
    except Exception:
        pass  # homepage may fail while API still works; cookie error surfaces later

    await _throttle()

    try:
        resp = await client.get(
            f"{settings.nse_base}{path}",
            params=params,
            headers={
                "Accept": "application/json",
                "Referer": f"{settings.nse_base}/",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise UpstreamUnavailableError(
            f"NSE request failed: {type(exc).__name__}: {exc or 'connection error (no detail)'}",
            hint="NSE aggressively throttles non-browser clients; retry in a minute.",
        ) from exc

    if resp.status_code in (401, 403):
        raise UpstreamUnavailableError(
            f"NSE blocked the request (HTTP {resp.status_code}).",
            hint="Cookie handshake may have expired or NSE is rate-limiting this IP; retry shortly.",
        )
    if resp.status_code == 404:
        raise DataNotAvailableError(f"NSE has no data at {path} for these parameters.")
    if resp.status_code >= 400:
        raise UpstreamUnavailableError(f"NSE returned HTTP {resp.status_code} for {path}.")

    try:
        return resp.json()
    except json.JSONDecodeError as exc:
        raise UpstreamUnavailableError(
            "NSE returned a non-JSON response (likely a bot-challenge page).",
            hint="Retry in a few minutes; raw upstream content is never forwarded.",
        ) from exc


# --- public provider functions -------------------------------------------------


async def get_quote(symbol: str) -> dict:
    symbol = symbol.strip().upper()
    if not symbol or len(symbol) > 30:
        raise ValueError("symbol must be 1-30 characters")

    async def _factory() -> dict:
        payload = await _nse_get_json("/api/quote-equity", {"symbol": symbol})
        price = payload.get("priceInfo") or {}
        if not price:
            raise DataNotAvailableError(f"NSE returned no price data for '{symbol}'.")
        data = {
            "symbol": symbol,
            "company_name": (payload.get("info") or {}).get("companyName"),
            "last_price": price.get("lastPrice"),
            "change": price.get("change"),
            "change_percent": price.get("pChange"),
            "open": price.get("open"),
            "day_high": price.get("intraDayHighLow", {}).get("max")
            if isinstance(price.get("intraDayHighLow"), dict)
            else None,
            "day_low": price.get("intraDayHighLow", {}).get("min")
            if isinstance(price.get("intraDayHighLow"), dict)
            else None,
            "previous_close": price.get("previousClose"),
            "volume": (payload.get("preOpenMarket") or {}).get("totalTradedVolume"),
            "market_status_note": "NSE is open 09:15-15:30 IST on trading days; quotes are delayed snapshots.",
        }
        return envelope(
            data,
            source=NSE_SOURCE,
            reference=NSE_REF,
            note="Unofficial public endpoint; quotes may be delayed/intraday. Not investment advice.",
        )

    return await nse_cache.get_or_set(f"nse:quote:{symbol}", _factory, settings.ttl_nse_quote)


async def get_index_quote(index_name: str = "NIFTY 50") -> dict:
    index_name = index_name.strip().upper()
    async def _factory() -> dict:
        payload = await _nse_get_json("/api/equity-stockIndices", {"index": index_name})
        rows = payload.get("data") or []
        row = next((r for r in rows if (r.get("symbol") or "").upper() == index_name), None)
        if row is None:
            raise DataNotAvailableError(
                f"Index '{index_name}' not found; try 'NIFTY 50', 'NIFTY BANK', 'NIFTY IT', 'NIFTY MIDCAP 100'."
            )
        return envelope(
            {
                "index": row.get("symbol") or index_name,
                "last": row.get("last"),
                "change": row.get("change"),
                "change_percent": row.get("percChange"),
                "open": row.get("open"),
                "day_high": row.get("dayHigh"),
                "day_low": row.get("dayLow"),
                "year_high": row.get("yearHigh"),
                "year_low": row.get("yearLow"),
                "advances": row.get("advances"),
                "declines": row.get("declines"),
            },
            source=NSE_SOURCE,
            reference=NSE_REF,
            note="Unofficial public endpoint; values are intraday snapshots.",
        )
    return await nse_cache.get_or_set(f"nse:index:{index_name}", _factory, settings.ttl_nse_quote)


async def get_historical(symbol: str, from_date: str, to_date: str | None = None) -> dict:
    symbol = symbol.strip().upper()
    try:
        frm = date.fromisoformat(from_date)
    except ValueError as exc:
        raise ValueError(f"Invalid from_date '{from_date}'; use YYYY-MM-DD") from exc
    to = date.fromisoformat(to_date) if to_date else date.today()
    if to < frm:
        raise ValueError("to_date must be on/after from_date")
    if (to - frm).days > 366:
        raise ValueError("Range exceeds 366 days; NSE historical API caps the window - split your request.")

    payload = await _nse_get_json(
        "/api/historical/cm/equity",
        {
            "symbol": symbol,
            "from": frm.strftime("%d-%m-%Y"),
            "to": to.strftime("%d-%m-%Y"),
        },
    )
    rows = payload.get("data") or []
    if not rows:
        raise DataNotAvailableError(f"No historical rows for {symbol} between {frm} and {to}.")
    history = [
        {
            "date": r.get("mTIMESTAMP"),
            "open": r.get("CH_OPENING_PRICE"),
            "high": r.get("CH_TRADE_HIGH_PRICE"),
            "low": r.get("CH_TRADE_LOW_PRICE"),
            "close": r.get("CH_CLOSING_PRICE"),
            "last": r.get("CH_LAST_TRADED_PRICE"),
            "previous_close": r.get("CH_PREVIOUS_CLS_PRICE"),
            "volume": r.get("CH_TOT_TRADED_QTY"),
        }
        for r in rows
    ]
    return envelope(
        {"symbol": symbol, "from_date": frm.isoformat(), "to_date": to.isoformat(), "rows": history, "count": len(history)},
        source=NSE_SOURCE,
        reference=NSE_REF,
        note="Unofficial public endpoint; OHLCV as published by NSE.",
    )


async def market_status() -> dict:
    payload = await _nse_get_json("/api/marketStatus")
    return envelope(
        payload,
        source=NSE_SOURCE,
        reference=NSE_REF,
        note="Unofficial public endpoint.",
    )
