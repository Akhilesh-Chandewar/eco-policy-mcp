"""Server assembly and entry points.

Two transports, any MCP client:
- stdio (default): local clients (Claude Desktop, Cursor, Gemini CLI, ...)
- streamable-http: remote/web clients (`eco-policy-mcp --http --port 8000`)
"""

from __future__ import annotations

import argparse
import logging

from fastmcp import FastMCP

from . import __version__
from .tools import register_tools

logger = logging.getLogger("eco-policy-mcp")


def create_server() -> FastMCP:
    mcp = FastMCP(
        name="eco-policy-mcp",
        version=__version__,
        instructions=(
            "Indian finance data & calculators for AI agents: mutual-fund NAVs "
            "(AMFI), GST and income-tax computations, RBI policy rates, and NSE "
            "market data. Every successful response carries a `provenance` block "
            "(source + as_of) - cite it instead of guessing. All tools work with "
            "any MCP client; quote data comes from unofficial public endpoints "
            "and may be delayed. Nothing here is investment advice."
        ),
    )
    register_tools(mcp)
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="eco-policy-mcp",
        description="MCP server for Indian finance data (any MCP client).",
    )
    parser.add_argument(
        "--http", action="store_true", help="serve streamable-HTTP instead of stdio"
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default 8000)")
    parser.add_argument("--version", action="version", version=f"eco-policy-mcp {__version__}")
    parser.add_argument("--log-level", default="INFO", help="logging level")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    mcp = create_server()

    if args.http:
        logger.info("eco-policy-mcp %s serving streamable-HTTP on http://%s:%d/mcp", __version__, args.host, args.port)
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        logger.debug("eco-policy-mcp %s serving on stdio", __version__)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
