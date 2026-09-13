"""eco-policy-mcp: an MCP server for Indian finance data.

Exposes mutual-fund NAVs (AMFI), GST & income-tax calculators, RBI policy
rates and NSE market data as MCP tools, resources and prompts. Designed for
ANY MCP-compatible client (Claude, Cursor, Gemini CLI, VS Code, Cline,
custom agents, ...) over stdio or streamable-HTTP transports.

Every value returned carries provenance (source + as-of timestamp), so AI
clients can cite where each number came from instead of hallucinating.
"""

__version__ = "0.1.0"
