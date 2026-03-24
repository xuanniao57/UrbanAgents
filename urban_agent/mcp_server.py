# MCP Server has been removed.
# UrbanAgent uses CLI as the tool interface for LLM agents.
# See: python -m urban_agent --help
# See: QUICK_DEPLOY.md
raise ImportError(
    "mcp_server.py is deprecated. "
    "Use `python -m urban_agent <command>` instead. "
    "See QUICK_DEPLOY.md for details."
)
