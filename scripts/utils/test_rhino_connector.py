"""
Smoke test for the UrbanAgent Rhino / Grasshopper connector.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_env_file() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["health", "evaluate", "hops", "command"], default="health")
    parser.add_argument("--definition-path", default="")
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--inputs-json", default="{}")
    parser.add_argument("--arguments-json", default="{}")
    return parser.parse_args()


def main() -> None:
    load_env_file()
    args = parse_args()

    from urban_agent.mcp_tools import UrbanMCPTools

    tools = UrbanMCPTools()
    if args.mode == "health":
        result = tools.execute_tool("rhino_health_check", {})
    elif args.mode == "evaluate":
        result = tools.execute_tool(
            "evaluate_grasshopper_definition",
            {
                "definition_path": args.definition_path,
                "input_values": json.loads(args.inputs_json),
            },
        )
    elif args.mode == "hops":
        result = tools.execute_tool(
            "call_grasshopper_hops",
            {
                "endpoint": args.endpoint,
                "input_values": json.loads(args.inputs_json),
            },
        )
    else:
        result = tools.execute_tool(
            "invoke_rhino_compute",
            {
                "endpoint": args.endpoint,
                "arguments": json.loads(args.arguments_json),
            },
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()