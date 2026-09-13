"""AMFI provider tests: NAVAll parsing, search, NAV, history, returns, SIP, XIRR."""

from __future__ import annotations

from datetime import date

import pytest

from eco_policy_mcp.errors import DataNotAvailableError, ValidationError
from eco_policy_mcp.providers import amfi


async def test_navall_parsing(amfi_sample):
    schemes = await amfi._fetch_navall()
    assert len(schemes) == 7
    hdfc = next(s for s in schemes if s["scheme_code"] == "119063")
    assert hdfc["scheme_name"] == "HDFC Balanced Advantage Fund - Growth"
    assert hdfc["amc"] == "HDFC Mutual Fund"
    assert hdfc["isin_growth"] == "INF179K01XQ2"
    assert hdfc["isin_div_payout"] == "INF179K01XQ1"
    assert hdfc["nav"] == pytest.approx(498.23)
    assert hdfc["nav_date"] == "2026-09-05"


async def test_navall_parsing_names_with_semicolons(amfi_sample):
    """Real-file layout: names can contain ';' segments (plan/option)."""
    schemes = await amfi._fetch_navall()
    row = next(s for s in schemes if s["scheme_code"] == "151165")
    assert row["scheme_name"] == "360 ONE ELSS Tax Saver Nifty 50 Index Fund;Direct Plan;GROWTH Option"
    assert row["nav"] == pytest.approx(13.3144)
    assert row["nav_date"] == "2026-09-11"


async def test_search_schemes(amfi_sample):
    out = await amfi.search_schemes("nifty 50")
    assert out["data"]["total_matches"] == 3
    names = [s["scheme_name"] for s in out["data"]["schemes"]]
    assert all("Nifty 50" in n for n in names)
    assert out["provenance"]["source"].startswith("AMFI")


async def test_search_requires_two_chars(amfi_sample):
    with pytest.raises(ValidationError):
        await amfi.search_schemes("n")


async def test_get_nav(amfi_sample):
    out = await amfi.get_nav("120754")
    assert out["data"]["nav"] == pytest.approx(268.85)
    assert out["data"]["amc"] == "ICICI Prudential Mutual Fund"


async def test_get_nav_unknown_code(amfi_sample):
    with pytest.raises(DataNotAvailableError):
        await amfi.get_nav("999999")


HISTORY = [
    {"date": "2023-12-29", "nav": 90.0},
    {"date": "2024-01-05", "nav": 100.0},
    {"date": "2024-02-05", "nav": 200.0},
    {"date": "2024-03-05", "nav": 250.0},
    {"date": "2024-04-05", "nav": 300.0},
    {"date": "2024-06-28", "nav": 350.0},
]


async def test_nav_history_date_filter(history_patch):
    history_patch(HISTORY)
    out = await amfi.get_nav_history("119063", "2024-01-01", "2024-04-30")
    assert out["data"]["count"] == 4
    assert out["data"]["rows"][0]["date"] == "2024-01-05"


async def test_nav_history_bad_date(history_patch):
    history_patch(HISTORY)
    with pytest.raises(ValidationError):
        await amfi.get_nav_history("119063", "01-2024-01")


async def test_compute_returns_weekend_stepback(history_patch):
    history_patch(HISTORY)
    # 2024-01-01 is a holiday -> steps back to 2023-12-29 (nav 90)
    # 2024-07-01 steps back to 2024-06-28 (nav 350); 183 days -> no CAGR
    out = await amfi.compute_returns("119063", "2024-01-01", "2024-07-01")
    d = out["data"]
    assert d["from_date"] == "2023-12-29"
    assert d["to_date"] == "2024-06-28"
    assert d["absolute_return_percent"] == pytest.approx(288.89, abs=0.01)
    assert d["cagr_percent"] is None


async def test_sip_calculator_exact_units(history_patch):
    history_patch(HISTORY)
    # SIPs on the 5th: Jan-5, Feb-5, Mar-5, Apr-5 (inclusive) = 4 instalments
    out = await amfi.sip_calculator("119063", 1000.0, "2024-01-05", "2024-04-05")
    d = out["data"]
    assert d["installments"] == 4
    assert d["total_invested"] == 4000.0
    # units = 1000/100 + 1000/200 + 1000/250 + 1000/300 = 10+5+4+3.3333
    assert d["units_accumulated"] == pytest.approx(22.3333, abs=1e-3)
    assert d["current_value"] == pytest.approx(6700.0)  # 22.3333 * 300
    assert d["absolute_gain"] == pytest.approx(2700.0)


def test_xirr_exact_one_year():
    # 2024 is a leap year: 366 days over a 365.25-day year convention
    # gives 1.1^(365.25/366)-1 = 0.099785, not exactly 0.10.
    cf = [(date(2024, 1, 1), -1000.0), (date(2025, 1, 1), 1100.0)]
    assert amfi._xirr(cf) == pytest.approx(0.099785, abs=1e-4)


def test_xirr_no_sign_change_raises():
    cf = [(date(2024, 1, 1), -1000.0), (date(2025, 1, 1), -500.0)]
    with pytest.raises(ValidationError):
        amfi._xirr(cf)
