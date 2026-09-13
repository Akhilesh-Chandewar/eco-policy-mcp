# eco-policy-mcp

**An MCP server for Indian finance data** — mutual-fund NAVs, GST &
income-tax calculators, RBI policy rates and NSE market data — built for
**any MCP client** (Claude, Cursor, Gemini CLI, VS Code, Cline, custom
agents...), not just one.

Every successful response carries a **provenance block** (`source`, `as_of`,
`reference`), so AI agents can cite where each number came from instead of
hallucinating it.

## Install & run

```bash
# Run with any MCP client via uvx (once published):
uvx eco-policy-mcp

# From a clone:
uv sync
uv run eco-policy-mcp            # stdio (default, local clients)
uv run eco-policy-mcp --http --port 8000   # streamable-HTTP (remote clients)
```

See [`examples/`](examples/README.md) for client configs (Claude Desktop,
Cursor, Gemini CLI, VS Code, remote HTTP).

## Tools

| Domain | Tool | What it does |
|---|---|---|
| GST | `gst_split` | CGST/SGST vs IGST breakup for an amount + slab rate |
| GST | `gst_from_inclusive` | Extract GST from a tax-inclusive amount |
| GST | `gst_reverse_charge` | Reverse-charge (RCM) tax payable |
| GST | `gstin_validate` | GSTIN mod-36 checksum validation + state code |
| Income tax | `income_tax_new_regime` | FY 2026-27 new-regime estimate (std deduction + 87A rebate) |
| Income tax | `income_tax_old_regime` | Old-regime estimate (80C, age-based exemption) |
| Income tax | `income_tax_compare_regimes` | New vs old with recommendation |
| Mutual funds | `mf_search_schemes` | Search all AMFI schemes by name |
| Mutual funds | `mf_get_nav` | Latest NAV for a scheme code |
| Mutual funds | `mf_get_nav_history` | Historical NAVs between dates |
| Mutual funds | `mf_compute_returns` | Absolute return + CAGR between dates |
| Mutual funds | `mf_sip_calculator` | SIP simulation on real NAVs with XIRR |
| RBI | `rbi_get_policy_rates` | Repo, SDF, MSF, bank rate, CRR, SLR (as-of dated) |
| NSE | `nse_get_quote` | Equity quote (unofficial public endpoint) |
| NSE | `nse_get_index_quote` | Index snapshot (NIFTY 50, BANK, IT...) |
| NSE | `nse_get_historical` | Daily OHLCV (max 1y window) |
| Server | `eco_server_info` | Version, tool list, cache health |

Also exposes **resources** (`eco-policy://amfi/freshness`,
`eco-policy://rbi/policy-rates`) and **prompts** (`compare_mutual_funds`,
`gst_invoice_breakup`).

## Data sources & disclaimers

- **AMFI** (`NAVAll.txt`) — official daily NAV dump; parsed and cached 6h.
- **mfapi.in** — community mirror of AMFI's NAV archive (history, returns, SIP).
- **RBI** — curated policy-rate snapshot stamped with its as-of date; verify at
  [rbi.org.in](https://www.rbi.org.in) before acting on it.
- **NSE** — unofficial public endpoints; quotes may be delayed and endpoints
  can change without notice. Failures return structured errors, never raw HTML.
- Tax computations are **estimators** (excludes surcharge, capital-gains
  special rates); nothing here is investment or tax advice.

## Configuration

All settings via env vars (prefix `ECO_`): `ECO_TTL_AMFI_INDEX`,
`ECO_TTL_NSE_QUOTE`, `ECO_NSE_MIN_INTERVAL`, `ECO_HTTP_TIMEOUT`,
`ECO_MFAPI_BASE`, `ECO_NSE_BASE`, `ECO_AMFI_NAV_URL`, ... — see
`src/eco_policy_mcp/config.py`.

## Development

```bash
uv sync --dev          # install with dev tools
uv run pytest          # run the test suite (no network needed)
```

## License

MIT — see [LICENSE](LICENSE).
