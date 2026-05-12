# UrbanAgent Tool Surfaces

UrbanAgent keeps two tool surfaces separate.

## Domain tools

These are small urban-analysis tools: OSM/context acquisition, source diagnostics,
metric computation, and GIS artifact export. They should compute or export data;
policy thresholds and case-specific interpretation should come from memory.

## Agent tools

`agent_toolkit.py` adapts the useful Hermes-style pattern:

- built-in toolsets such as `web`, `file`, `browser`, `planning_memory`, `kanban`,
  `terminal`, and `execution_delegation`;
- a schema + handler registry for function-calling runtimes;
- gated risky operations, where file-write, terminal, code, and process tools
  require explicit environment flags;
- manifest-based extension through `register_agent_tool_manifest()`.

Default UrbanAgent analysis does not expose every agent tool. Runtimes opt in:

```python
from plugins.mcp import get_mcp_tools

tools = get_mcp_tools(include_agent_tools=True, agent_toolsets=["planning_memory", "file"])
```

User tools can be added with a manifest:

```json
{
  "tools": [
    {
      "name": "my_tool",
      "description": "Run my project-specific operation.",
      "parameters": {"type": "object", "properties": {}, "additionalProperties": true},
      "python_function": "my_package.my_tools:my_tool"
    }
  ]
}
```

The Python function should accept one `dict` argument and return a JSON-serializable
`dict`.
