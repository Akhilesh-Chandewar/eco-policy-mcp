"""MCP tool definitions.

Thin layer: validate input, call provider, catch any exception and convert to
the standard structured error payload. Any MCP client (Claude, Cursor,
Gemini CLI, VS Code, Cline, custom agents) sees identical behaviour.
"""

from __future__ import annotations

from functools import wraps

from ..errors import to_error_payload
from ..providers import amfi, gst, income_tax, nse, rbi
from ..cache import amfi_cache, nse_cache


def _guard(fn):
    """Convert raised errors into structured payloads; preserve the signature
    (FastMCP inspects it to build the tool schema)."""

    @wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            return to_error_payload(exc)

    return wrapper


FALLBACK_TOOL_NAMES = [
    "gst_split",
    "gst_from_inclusive",
    "gst_reverse_charge",
    "gstin_validate",
    "income_tax_new_regime",
    "income_tax_old_regime",
    "income_tax_compare_regimes",
    "mf_search_schemes",
    "mf_get_nav",
    "mf_get_nav_history",
    "mf_compute_returns",
    "mf_sip_calculator",
    "rbi_get_policy_rates",
    "nse_get_quote",
    "nse_get_index_quote",
    "nse_get_historical",
    "eco_server_info",
]


def _list_tools(server) -> list[str]:
    try:
        tm = getattr(server, "_tool_manager", None)
        tools = getattr(tm, "tools", None) if tm is not None else None
        if isinstance(tools, dict):
            return sorted(tools.keys())
        if isinstance(tools, list):
            return sorted(getattr(t, "name", str(t)) for t in tools)
    except Exception:  # noqa: BLE001 - introspection is best-effort
        pass
    return list(FALLBACK_TOOL_NAMES)


def register_tools(mcp_server) -> None:
    """Attach all tools/resources/prompts to a FastMCP instance."""
    server = mcp_server  # capture for closures (never via a mutable global)

    # --- GST ----------------------------------------------------------------
    @server.tool(tags={"gst", "tax", "india"})
    @_guard
    async def gst_split(amount: float, rate_percent: float, intra_state: bool) -> dict:
        """Split GST into CGST+SGST (intra-state) or IGST (inter-state).

        Args:
            amount: Taxable base amount in INR.
            rate_percent: GST slab rate - one of 0.25, 3, 5, 12, 18, 28.
            intra_state: True if supplier and place of supply are in the same state.
        """
        return gst.gst_split(amount, rate_percent, intra_state)

    @server.tool(tags={"gst", "tax", "india"})
    @_guard
    async def gst_from_inclusive(amount: float, rate_percent: float) -> dict:
        """Extract GST out of a tax-inclusive (MRP-style) amount.

        Args:
            amount: Gross amount that already includes GST.
            rate_percent: GST slab rate - one of 0.25, 3, 5, 12, 18, 28.
        """
        return gst.gst_from_inclusive(amount, rate_percent)

    @server.tool(tags={"gst", "tax", "india"})
    @_guard
    async def gst_reverse_charge(amount: float, rate_percent: float) -> dict:
        """Compute tax payable under reverse charge mechanism (Section 9(3)/9(4)).

        Args:
            amount: Taxable base amount in INR.
            rate_percent: GST slab rate - one of 0.25, 3, 5, 12, 18, 28.
        """
        return gst.gst_reverse_charge(amount, rate_percent)

    @server.tool(tags={"gst", "compliance"})
    @_guard
    async def gstin_validate(gstin: str) -> dict:
        """Validate an Indian GSTIN using its mod-36 checksum and extract the state code.

        Args:
            gstin: 15-character GSTIN to validate.
        """
        valid = gst.validate_gstin(gstin)
        from ..models import utcnow

        return {
            "data": {
                "gstin": gstin.strip().upper(),
                "is_valid": valid,
                "state_code": gst.state_code_from_gstin(gstin) if len(gstin.strip()) >= 2 else None,
            },
            "provenance": {
                "source": "GSTN GSTIN checksum specification",
                "as_of": utcnow().isoformat(),
                "reference": "https://www.gstn.org.in",
                "note": "Checksum validates format only; active registration status must be checked on gst.gov.in.",
            },
        }

    # --- income tax ----------------------------------------------------------
    @server.tool(tags={"tax", "income-tax", "india"})
    @_guard
    async def income_tax_new_regime(gross_salary: float, age: int = 35) -> dict:
        """Estimate income tax for FY 2026-27 (AY 2027-28) under the NEW regime.

        Applies the standard deduction (Rs 75,000) and the Section 87A rebate
        (taxable income up to Rs 12,00,000 effectively tax-free). Excludes
        surcharge and capital-gains special rates.

        Args:
            gross_salary: Annual gross salary in INR.
            age: Age of the taxpayer (no slab effect in the new regime; kept for parity).
        """
        return income_tax.income_tax_new_regime(gross_salary, age)

    @server.tool(tags={"tax", "income-tax", "india"})
    @_guard
    async def income_tax_old_regime(
        gross_salary: float, deductions_80c: float = 0.0, other_deductions: float = 0.0, age: int = 35
    ) -> dict:
        """Estimate income tax for FY 2026-27 (AY 2027-28) under the OLD regime.

        Args:
            gross_salary: Annual gross salary in INR.
            deductions_80c: Chapter VI-A 80C investments (capped at Rs 1.5 lakh).
            other_deductions: Other deductions (80D, HRA, etc.) - pass the eligible amount.
            age: Age of the taxpayer (senior/super-senior exemption limits apply).
        """
        return income_tax.income_tax_old_regime(gross_salary, deductions_80c, other_deductions, age)

    @server.tool(tags={"tax", "income-tax", "india"})
    @_guard
    async def income_tax_compare_regimes(
        gross_salary: float, deductions_80c: float = 0.0, other_deductions: float = 0.0, age: int = 35
    ) -> dict:
        """Compare NEW vs OLD regime tax for FY 2026-27 and recommend the cheaper one.

        Args:
            gross_salary: Annual gross salary in INR.
            deductions_80c: 80C investments (old regime only, capped at Rs 1.5 lakh).
            other_deductions: Other old-regime deductions.
            age: Age of the taxpayer.
        """
        return income_tax.compare_regimes(gross_salary, deductions_80c, other_deductions, age)

    # --- mutual funds ----------------------------------------------------------
    @server.tool(tags={"mutual-funds", "amfi", "india"})
    @_guard
    async def mf_search_schemes(query: str, limit: int = 25) -> dict:
        """Search all Indian mutual fund schemes by name (AMFI official directory).

        Args:
            query: Substring to search in scheme names (min 2 chars), e.g. 'nifty 50' or 'hdfc balanced'.
            limit: Max results to return (1-100).
        """
        return await amfi.search_schemes(query, min(max(int(limit), 1), 100))

    @server.tool(tags={"mutual-funds", "amfi", "india"})
    @_guard
    async def mf_get_nav(scheme_code: str) -> dict:
        """Get the latest published NAV for a mutual fund scheme (AMFI official data).

        Args:
            scheme_code: AMFI scheme code (find via mf_search_schemes).
        """
        return await amfi.get_nav(scheme_code)

    @server.tool(tags={"mutual-funds", "amfi", "india"})
    @_guard
    async def mf_get_nav_history(scheme_code: str, from_date: str | None = None, to_date: str | None = None) -> dict:
        """Get historical NAVs for a scheme between dates (ISO YYYY-MM-DD, inclusive).

        Args:
            scheme_code: AMFI scheme code.
            from_date: Start date YYYY-MM-DD (optional).
            to_date: End date YYYY-MM-DD (optional).
        """
        return await amfi.get_nav_history(scheme_code, from_date, to_date)

    @server.tool(tags={"mutual-funds", "returns", "india"})
    @_guard
    async def mf_compute_returns(scheme_code: str, from_date: str, to_date: str | None = None) -> dict:
        """Compute absolute return and CAGR for a scheme between two dates.

        Args:
            scheme_code: AMFI scheme code.
            from_date: Start date YYYY-MM-DD.
            to_date: End date YYYY-MM-DD (defaults to the latest NAV date).
        """
        return await amfi.compute_returns(scheme_code, from_date, to_date)

    @server.tool(tags={"mutual-funds", "sip", "planning", "india"})
    @_guard
    async def mf_sip_calculator(
        scheme_code: str, monthly_amount: float, from_date: str, to_date: str | None = None
    ) -> dict:
        """Simulate a monthly SIP in a scheme using actual historical NAVs (XIRR included).

        Args:
            scheme_code: AMFI scheme code.
            monthly_amount: SIP instalment in INR.
            from_date: First instalment month YYYY-MM-DD.
            to_date: Last valuation date YYYY-MM-DD (defaults to latest NAV date).
        """
        return await amfi.sip_calculator(scheme_code, monthly_amount, from_date, to_date)

    # --- RBI ---------------------------------------------------------------------
    @server.tool(tags={"rbi", "rates", "macro", "india"})
    @_guard
    async def rbi_get_policy_rates() -> dict:
        """Get current RBI policy rates (repo, SDF, MSF, bank rate, CRR, SLR) with as-of date."""
        return rbi.get_policy_rates()

    # --- market data ----------------------------------------------------------------
    @server.tool(tags={"equities", "nse", "india"})
    @_guard
    async def nse_get_quote(symbol: str) -> dict:
        """Get a live NSE equity quote (unofficial public endpoint).

        Args:
            symbol: NSE trading symbol, e.g. 'INFY', 'RELIANCE', 'TCS'.
        """
        return await nse.get_quote(symbol)

    @server.tool(tags={"equities", "nse", "india"})
    @_guard
    async def nse_get_index_quote(index_name: str = "NIFTY 50") -> dict:
        """Get a live NSE index snapshot (NIFTY 50, NIFTY BANK, NIFTY IT, ...).

        Args:
            index_name: Index name, e.g. 'NIFTY 50', 'NIFTY BANK', 'NIFTY MIDCAP 100'.
        """
        return await nse.get_index_quote(index_name)

    @server.tool(tags={"equities", "nse", "india"})
    @_guard
    async def nse_get_historical(symbol: str, from_date: str, to_date: str | None = None) -> dict:
        """Get NSE daily OHLCV history for a symbol (max 1 year window per call).

        Args:
            symbol: NSE trading symbol.
            from_date: Start date YYYY-MM-DD.
            to_date: End date YYYY-MM-DD (defaults to today).
        """
        return await nse.get_historical(symbol, from_date, to_date)

    # --- server diagnostics -------------------------------------------------------------
    @server.tool(tags={"diagnostics"})
    @_guard
    async def eco_server_info() -> dict:
        """Server version, registered tools and cache health - useful for debugging connectivity."""
        from .. import __version__

        return {
            "data": {
                "server": "eco-policy-mcp",
                "version": __version__,
                "clients": "works with ANY MCP client (stdio or streamable-http)",
                "tools": _list_tools(server),
                "cache": {"amfi": amfi_cache.stats(), "nse": nse_cache.stats()},
            },
            "provenance": {
                "source": "server introspection",
                "as_of": None,
                "reference": None,
                "note": None,
            },
        }

    # --- resources --------------------------------------------------------------------
    @server.resource("eco-policy://amfi/freshness")
    async def amfi_freshness() -> str:
        """Freshness of the cached AMFI NAV index (which NAV date it reflects)."""
        fresh = await amfi.nav_index_freshness()
        return f"AMFI NAV file date: {fresh.isoformat() if fresh else 'unknown'} (cache TTL 6h)"

    @server.resource("eco-policy://rbi/policy-rates")
    async def rbi_rates_resource() -> str:
        """RBI policy rates snapshot (same data as the rbi_get_policy_rates tool)."""
        import json

        return json.dumps(rbi.get_policy_rates()["data"], indent=2)

    # --- prompts -----------------------------------------------------------------------
    @server.prompt
    def compare_mutual_funds(scheme_a: str, scheme_b: str) -> str:
        """Prompt template: compare two mutual fund schemes on returns."""
        return (
            f"Compare Indian mutual fund schemes '{scheme_a}' and '{scheme_b}'.\n"
            "Use mf_search_schemes to resolve each name to a scheme_code, then mf_compute_returns "
            "for 1Y and 3Y windows. Present absolute returns and CAGR side by side with the as-of "
            "dates from provenance, and note that NAV-based returns exclude loads/taxes."
        )

    @server.prompt
    def gst_invoice_breakup(amount: float, rate_percent: float, intra_state: bool) -> str:
        """Prompt template: produce an invoice-ready GST breakup."""
        return (
            f"Prepare an invoice-style GST breakup for a base amount of Rs {amount} at {rate_percent}% GST, "
            f"intra-state supply: {intra_state}. Call gst_split for the tax components and present "
            "base, CGST, SGST/IGST and invoice total in a table."
        )
