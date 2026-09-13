# PLAN — eco-policy-mcp

MCP server for Indian finance data (mutual funds, GST/tax, RBI, NSE) usable
from **any MCP client** over stdio or streamable-HTTP.

## Principles

1. **Client-agnostic**: pure MCP spec compliance; no Claude/Cursor-specific code.
2. **Provenance everywhere**: every response carries `source` + `as_of`.
3. **Structured errors, never raw HTML**: agents can react to
   `{error: {code, message, hint}}`.
4. **Cache by data cadence**: NAV 6h, history 12h, quotes 60s, policy rates until changed.
5. **Thin tool layer over providers**: a new data source = one provider file.

## Phases

- [x] **Phase 0 — Skeleton**: uv project, FastMCP server, stdio + HTTP entry points.
- [x] **Phase 1 — Core domains**: GST (4 tools), income tax FY 2026-27 (3 tools),
      AMFI NAVs (5 tools incl. SIP + XIRR), RBI snapshot, error contract, caches,
      40+ tests, examples for five client types.
- [ ] **Phase 2 — Hardening & markets**: NSE resilience soak, registry submissions
      (Pulse, glama, Smithery), CI badge, PyPI publish (`uvx eco-policy-mcp`).
- [ ] **Phase 3 — Breadth**: SEBI/MCA filings, company financials (yfinance),
      EMI/gratuity/HRA tools, resource templates (`nav://scheme/{code}`).
- [ ] **Phase 4 — Hosted**: multi-tenant HTTP deployment, API keys, paid tier.

## Risk register

| Risk | Mitigation |
|---|---|
| NSE blocks scraping | Self-throttle, cookie handshake, structured errors; not on MVP critical path |
| Stale/wrong data | Mandatory provenance + as-of; curated RBI snapshot is explicitly dated |
| AMFI format change | Parser is fixture-tested; parse failure raises upstream error, not silent wrong data |
| Tax law changes | Slabs in one module with tests pinned to hand-computed values |
| Client quirks | Version-tolerant introspection; in-memory MCP client tests prove spec compliance |
