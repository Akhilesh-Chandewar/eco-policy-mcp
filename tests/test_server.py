"""End-to-end tests over the in-memory MCP client: proves ANY MCP client can
discover and call every tool exactly the same way."""

from __future__ import annotations

import json

from fastmcp import Client

from eco_policy_mcp.server import create_server


def _payload(result) -> dict:
    """Version-tolerant extraction of the tool result payload."""
    data = getattr(result, "data", None)
    if data is not None:
        return data
    return json.loads(result.content[0].text)


async def test_all_tools_registered():
    async with Client(create_server()) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
        expected = {
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
        }
        assert expected <= names
        assert len(names) >= 17


async def test_tool_schemas_expose_args():
    async with Client(create_server()) as client:
        tools = {t.name: t for t in await client.list_tools()}
        schema = getattr(tools["gst_split"], "input_schema", None) or tools["gst_split"].inputSchema
        assert "amount" in schema.get("properties", {})
        assert "rate_percent" in schema.get("properties", {})


async def test_call_gst_split_over_mcp():
    async with Client(create_server()) as client:
        result = await client.call_tool(
            "gst_split", {"amount": 10_000, "rate_percent": 18, "intra_state": True}
        )
        payload = _payload(result)
        assert payload["data"]["cgst"] == 900.0
        assert payload["data"]["total_invoice_value"] == 11_800.0
        assert payload["provenance"]["source"]


async def test_call_income_tax_over_mcp():
    async with Client(create_server()) as client:
        result = await client.call_tool("income_tax_new_regime", {"gross_salary": 1_275_000})
        payload = _payload(result)
        assert payload["data"]["total_tax_payable"] == 0.0  # 87A rebate at 12L taxable


async def test_call_rbi_over_mcp():
    async with Client(create_server()) as client:
        result = await client.call_tool("rbi_get_policy_rates", {})
        payload = _payload(result)
        assert payload["data"]["policy_repo_rate"] == 5.25


async def test_errors_are_structured_over_mcp():
    async with Client(create_server()) as client:
        result = await client.call_tool("gst_split", {"amount": 100, "rate_percent": 17, "intra_state": True})
        payload = _payload(result)
        assert payload["error"]["code"] == "invalid_input"


async def test_server_info_diagnostics():
    async with Client(create_server()) as client:
        result = await client.call_tool("eco_server_info", {})
        payload = _payload(result)
        assert payload["data"]["server"] == "eco-policy-mcp"
        assert len(payload["data"]["tools"]) >= 17


async def test_resources_and_prompts_available():
    async with Client(create_server()) as client:
        resources = await client.list_resources()
        uris = {str(r.uri) for r in resources}
        assert "eco-policy://rbi/policy-rates" in uris

        prompts = await client.list_prompts()
        prompt_names = {p.name for p in prompts}
        assert {"compare_mutual_funds", "gst_invoice_breakup"} <= prompt_names


async def test_gstin_validate_tool():
    async with Client(create_server()) as client:
        result = await client.call_tool("gstin_validate", {"gstin": "27AAPFU0939F1ZV"})
        payload = _payload(result)
        assert payload["data"]["is_valid"] is True
        assert payload["data"]["state_code"] == "27"
