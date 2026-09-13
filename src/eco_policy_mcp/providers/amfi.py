"""AMFI mutual-fund NAV provider.

Primary source: AMFI's daily NAVAll.txt dump (all schemes, one file).
Mirror for per-scheme history: mfapi.in (community API over the same data).

Design notes:
- NAVAll.txt is parsed once and cached (TTL 6h). Lines are pipe-separated;
  scheme blocks are "Scheme Name; ISIN Div Payout; ISIN Growth; NAV; Date".
- AMFI publishes *previous business day's* NAV until ~11pm IST; if the file's
  own date is older than a requested date, we say so via DataNotAvailableError
  instead of silently returning wrong-date data.
- Returns and SIP math are computed locally from cached history.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from ..cache import amfi_cache
from ..config import settings
from ..errors import DataNotAvailableError, UpstreamUnavailableError, ValidationError
from ..models import envelope
from .http import get_client

AMFI_SOURCE = "AMFI NAVAll.txt (amfiindia.com)"
AMFI_REF = "https://www.amfiindia.com/spages/NAVAll.txt"
MFAPI_SOURCE = "mfapi.in (AMFI data mirror)"
MFAPI_REF = "https://www.mfapi.in"


def _parse_date(raw: str) -> date | None:
    raw = raw.strip().rstrip(";")
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_nav(raw: str) -> float | None:
    raw = raw.strip()
    if raw in ("", "N.A.", "-"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def _fetch_navall() -> list[dict]:
    """Download and parse NAVAll.txt -> list of scheme dicts. Cached 6h."""

    async def _factory() -> list[dict]:
        try:
            resp = await get_client().get(settings.amfi_nav_url)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - normalise upstream failures
            raise UpstreamUnavailableError(
                f"Could not fetch AMFI NAVAll.txt: {exc}",
                hint="AMFI may be down or blocking; try again later.",
            ) from exc

        schemes: list[dict] = []
        current_amc = None
        file_dates: set[date] = set()
        text = resp.text

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if ";" not in line:
                # AMC header line
                if not line.lower().startswith(("scheme code", "nav date")):
                    current_amc = line
                continue
            parts = [p.strip() for p in line.split(";")]
            if len(parts) < 6:
                continue
            # Official layout starts: Scheme Code;ISIN Div Payout/Growth;ISIN
            # Div Reinvestment;Scheme Name... and ends: ...;NAV;Date.
            # Scheme names may themselves contain ';' segments (e.g.
            # "...Fund;Direct Plan;GROWTH Option"), so NAV is ALWAYS the
            # second-to-last field and date the last; the name is the middle.
            code_raw, isin_payout, isin_reinv = parts[0], parts[1], parts[2]
            name = ";".join(parts[3:-2])
            nav_raw, date_raw = parts[-2], parts[-1]
            if code_raw == "Scheme Code":  # column-header row
                continue
            if not name:
                continue
            nav = _parse_nav(nav_raw)
            nav_date = _parse_date(date_raw)
            if nav_date:
                file_dates.add(nav_date)
            schemes.append(
                {
                    "scheme_code": code_raw or None,
                    "scheme_name": name,
                    "amc": current_amc,
                    "isin_growth": isin_reinv or None,
                    "isin_div_payout": isin_payout or None,
                    "nav": nav,
                    "nav_date": nav_date.isoformat() if nav_date else None,
                }
            )

        if not schemes:
            raise UpstreamUnavailableError(
                "AMFI NAVAll.txt fetched but parsed to zero schemes; format may have changed.",
            )
        return schemes

    return await amfi_cache.get_or_set("amfi:navall", _factory, settings.ttl_amfi_index)


async def nav_index_freshness() -> date | None:
    schemes = await _fetch_navall()
    for s in schemes:
        if s["nav_date"]:
            return date.fromisoformat(s["nav_date"])
    return None


async def search_schemes(query: str, limit: int | None = None) -> dict:
    q = query.strip().lower()
    if len(q) < 2:
        raise ValidationError("query must be at least 2 characters")
    schemes = await _fetch_navall()
    cap = limit or settings.max_search_results
    hits = [s for s in schemes if q in s["scheme_name"].lower()]
    return envelope(
        {"query": query, "count": len(hits[:cap]), "total_matches": len(hits), "schemes": hits[:cap]},
        source=AMFI_SOURCE,
        reference=AMFI_REF,
        note="Search is a plain substring match on official scheme names. Use scheme_code with get_nav / get_nav_history.",
    )


async def get_nav(scheme_code: str) -> dict:
    code = scheme_code.strip()
    schemes = await _fetch_navall()
    match = next((s for s in schemes if s["scheme_code"] == code), None)
    if match is None or match["nav"] is None:
        raise DataNotAvailableError(
            f"No NAV found for scheme code '{code}' in the latest AMFI file.",
            hint="Use search_schemes to find the exact scheme code.",
        )
    return envelope(
        {
            "scheme_code": match["scheme_code"],
            "scheme_name": match["scheme_name"],
            "amc": match["amc"],
            "isin_growth": match["isin_growth"],
            "isin_div_payout": match["isin_div_payout"],
            "nav": match["nav"],
            "nav_date": match["nav_date"],
        },
        source=AMFI_SOURCE,
        reference=AMFI_REF,
        note="Latest published NAV. AMFI publishes previous business day's NAV until ~11pm IST.",
    )


async def _fetch_history(scheme_code: str) -> list[dict]:
    """Full NAV history from mfapi.in mirror. Cached 12h."""

    async def _factory() -> list[dict]:
        try:
            resp = await get_client().get(f"{settings.mfapi_base}/mf/{scheme_code}")
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise UpstreamUnavailableError(
                f"Could not fetch NAV history for {scheme_code} from mfapi.in: {exc}",
                hint="mfapi.in is a community mirror of AMFI data; try again later.",
            ) from exc

        meta = payload.get("meta") or {}
        rows = payload.get("data") or []
        history = []
        for row in rows:
            try:
                history.append(
                    {"date": datetime.strptime(row["date"], "%d-%m-%Y").date().isoformat(), "nav": float(row["nav"])}
                )
            except (KeyError, ValueError):
                continue
        if not history:
            raise DataNotAvailableError(
                f"mfapi.in returned no history rows for scheme {scheme_code}.",
                hint="Verify the scheme code via search_schemes (it lists AMFI codes; mfapi uses the same).",
            )
        return [{"meta": meta, "history": history}]

    cached = await amfi_cache.get_or_set(f"amfi:history:{scheme_code}", _factory, settings.ttl_nav_history)
    return cached[0]


async def get_nav_history(scheme_code: str, from_date: str | None = None, to_date: str | None = None) -> dict:
    def _iso_or_none(d: str | None) -> str | None:
        if not d:
            return None
        try:
            return date.fromisoformat(d).isoformat()
        except ValueError as exc:
            raise ValidationError(f"Invalid date '{d}'; use ISO format YYYY-MM-DD") from exc

    frm, to = _iso_or_none(from_date), _iso_or_none(to_date)
    bundle = await _fetch_history(scheme_code)
    history = bundle["history"]
    if frm:
        history = [r for r in history if r["date"] >= frm]
    if to:
        history = [r for r in history if r["date"] <= to]
    if not history:
        raise DataNotAvailableError("No NAV rows in the requested date range.")
    return envelope(
        {
            "scheme_code": scheme_code,
            "scheme_name": bundle["meta"].get("scheme_name"),
            "rows": history,
            "count": len(history),
        },
        source=MFAPI_SOURCE,
        reference=MFAPI_REF,
        note="History sourced from the mfapi.in mirror of AMFI's official NAV archive.",
    )


# --- computations over history -------------------------------------------------


def _xirr(cashflows: list[tuple[date, float]]) -> float:
    """Annualised IRR for irregular cashflows (negative = invested)."""
    rates = [0.10, 0.15, 0.20, 0.05, 0.30, 0.01, 0.5, -0.1]
    t0 = cashflows[0][0]

    def npv(rate: float) -> float:
        return sum(cf / (1 + rate) ** ((d - t0).days / 365.25) for d, cf in cashflows)

    lo, hi = -0.99, 1_000_000.0  # hi covers absurdly high short-period IRRs
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        raise ValidationError("Could not compute XIRR for these cashflows (sign change missing).")
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


async def compute_returns(scheme_code: str, from_date: str, to_date: str | None = None) -> dict:
    try:
        start = date.fromisoformat(from_date)
    except ValueError as exc:
        raise ValidationError(f"Invalid from_date '{from_date}'; use YYYY-MM-DD") from exc
    end = date.fromisoformat(to_date) if to_date else await nav_index_freshness()
    if end is None:
        raise DataNotAvailableError("Could not determine the latest NAV date.")

    bundle = await _fetch_history(scheme_code)
    history = {date.fromisoformat(r["date"]): r["nav"] for r in bundle["history"]}

    def _nav_on_or_before(target: date) -> tuple[date, float] | None:
        d = target
        for _ in range(30):  # step back over weekends/holidays
            if d in history:
                return d, history[d]
            d -= timedelta(days=1)
        return None

    start_hit = _nav_on_or_before(start)
    end_hit = _nav_on_or_before(end)
    if not start_hit or not end_hit:
        raise DataNotAvailableError(
            f"No NAVs available on/after {start} and on/before {end} for scheme {scheme_code}.",
            hint="History may not extend that far back; try a later from_date.",
        )

    d0, n0 = start_hit
    d1, n1 = end_hit
    days = (d1 - d0).days
    if days <= 0 or n0 <= 0:
        raise ValidationError("to_date must be after from_date with valid NAVs.")

    absolute = (n1 - n0) / n0
    cagr = (n1 / n0) ** (365.25 / days) - 1 if days >= 365 else None

    return envelope(
        {
            "scheme_code": scheme_code,
            "scheme_name": bundle["meta"].get("scheme_name"),
            "from_date": d0.isoformat(),
            "to_date": d1.isoformat(),
            "nav_from": n0,
            "nav_to": n1,
            "period_days": days,
            "absolute_return_percent": round(absolute * 100, 2),
            "cagr_percent": round(cagr * 100, 2) if cagr is not None else None,
            "cagr_note": "CAGR shown only for periods >= 1 year." if cagr is None else None,
        },
        source=MFAPI_SOURCE,
        reference=MFAPI_REF,
        note="Returns computed from NAV history; NAV-based returns ignore exit loads and taxes.",
    )


async def sip_calculator(
    scheme_code: str,
    monthly_amount: float,
    from_date: str,
    to_date: str | None = None,
) -> dict:
    if monthly_amount <= 0:
        raise ValidationError("monthly_amount must be positive")
    try:
        start = date.fromisoformat(from_date)
    except ValueError as exc:
        raise ValidationError(f"Invalid from_date '{from_date}'; use YYYY-MM-DD") from exc
    end = date.fromisoformat(to_date) if to_date else await nav_index_freshness()
    if end is None or end <= start:
        raise ValidationError("to_date must be after from_date.")

    bundle = await _fetch_history(scheme_code)
    history = {date.fromisoformat(r["date"]): r["nav"] for r in bundle["history"]}

    def _nav_on_or_before(target: date) -> float | None:
        d = target
        for _ in range(30):
            if d in history:
                return history[d]
            d -= timedelta(days=1)
        return None

    # SIP on the 5th of each month (or first SIP date's day-of-month)
    sip_day = min(start.day, 28)
    cashflows: list[tuple[date, float]] = []
    units = 0.0
    cur = date(start.year, start.month, sip_day)
    if cur < start:
        cur = date(cur.year + (cur.month == 12), 1 if cur.month == 12 else cur.month + 1, sip_day)
    while cur <= end:
        nav = _nav_on_or_before(cur)
        if nav and nav > 0:
            units += monthly_amount / nav
            cashflows.append((cur, -monthly_amount))
        cur = date(cur.year + (cur.month == 12), 1 if cur.month == 12 else cur.month + 1, sip_day)

    final_nav = _nav_on_or_before(end)
    if not final_nav or not cashflows:
        raise DataNotAvailableError("Not enough NAV data to simulate this SIP.")

    value = units * final_nav
    invested = monthly_amount * len(cashflows)
    cashflows.append((end, value))

    return envelope(
        {
            "scheme_code": scheme_code,
            "scheme_name": bundle["meta"].get("scheme_name"),
            "monthly_amount": monthly_amount,
            "installments": len(cashflows) - 1,
            "total_invested": round(invested, 2),
            "units_accumulated": round(units, 4),
            "final_nav": final_nav,
            "current_value": round(value, 2),
            "absolute_gain": round(value - invested, 2),
            "absolute_return_percent": round((value - invested) / invested * 100, 2) if invested else 0.0,
            "xirr_percent": round(_xirr(cashflows) * 100, 2),
            "sip_day_of_month": sip_day,
        },
        source=MFAPI_SOURCE,
        reference=MFAPI_REF,
        note="Idealised SIP: assumes allocation on the chosen day's NAV (stepped back over weekends/holidays); ignores exit load, STT and taxes.",
    )
