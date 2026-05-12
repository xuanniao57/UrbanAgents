"""Compatibility shim for the optional MCP tool plugin.

The UrbanAgent kernel no longer imports or initializes MCP tools by default.
Import this module only when an application explicitly wants the plugin tool
surface.
"""

from plugins.mcp.mcp_tools import MCPTool, UrbanMCPTools, get_mcp_tools

__all__ = ["MCPTool", "UrbanMCPTools", "get_mcp_tools"]
