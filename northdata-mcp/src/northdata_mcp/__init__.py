"""northdata-mcp — MCP server for the NorthData API.

Built on FastMCP v3. Wraps the same ``NorthDataClient`` and ``CreditGuard``
used by the ``northdata-cli`` package so there is a single source of truth
for API behavior and credit accounting.
"""

from northdata_mcp.server import create_server, main

__version__ = "0.1.1"

__all__ = ["create_server", "main", "__version__"]
