"""Run the MCP server.

# stdio, e.g. for Claude Code / Claude Desktop (identity from AIP_MCP_AGENT)
AIP_MCP_AGENT=handler-assistant python -m aip.mcp --core-url http://localhost:8000

# Streamable HTTP for agent workers
python -m aip.mcp --transport http --port 8766 --core-url http://localhost:8000
"""

import argparse

import anyio
import httpx

from aip.mcp.core_client import CoreClient
from aip.mcp.server import build_server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--core-url", default="http://localhost:8000")
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 inside a container")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    async def run() -> None:
        async with httpx.AsyncClient(base_url=args.core_url, timeout=30) as http:
            server = build_server(CoreClient(http))
            if args.transport == "stdio":
                await server.run_stdio_async()
            else:
                await server.run_streamable_http_async(host=args.host, port=args.port)

    anyio.run(run)


if __name__ == "__main__":
    main()
