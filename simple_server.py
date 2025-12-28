# simple_server.py
from fastmcp import FastMCP

# 1. Create the server
mcp = FastMCP("demo")


# 2. Add a dummy tool so the agent sees something
@mcp.tool()
def ping() -> str:
    return "pong"


# 3. Add a calculator tool (just to be safe)
@mcp.tool()
def add(a: int, b: int) -> int:
    return a + b


if __name__ == "__main__":
    print("🚀 Starting Simple MCP Server on port 8000 (SSE Mode)...")
    # FORCE transport='sse' to open the network port
    mcp.run(transport="sse", port=8000, host="0.0.0.0")
