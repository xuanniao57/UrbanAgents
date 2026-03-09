"""
Rhino.Compute and Grasshopper connector implementations.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseConnector


class RhinoComputeConnector(BaseConnector):
    def __init__(
        self,
        name: str = "rhino_compute",
        config: Optional[Dict[str, Any]] = None,
    ):
        merged = {
            "base_url": os.getenv("RHINO_COMPUTE_URL", "http://localhost:6500"),
            "api_key": os.getenv("RHINO_COMPUTE_API_KEY", ""),
            "timeout": int(os.getenv("RHINO_COMPUTE_TIMEOUT", "120")),
        }
        if config:
            merged.update(config)
        super().__init__(name=name, config=merged)

    def health_check(self) -> Dict[str, Any]:
        try:
            response = self._request("GET", "/version")
            return {"success": True, "result": response}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def execute(self, operation: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}
        if operation == "health_check":
            return self.health_check()
        if operation == "evaluate_definition":
            return self.evaluate_grasshopper_definition(
                definition_path=payload.get("definition_path", ""),
                input_values=payload.get("input_values", {}),
                pointer=payload.get("pointer"),
            )
        if operation == "call_hops":
            return self.call_grasshopper_hops(
                endpoint=payload.get("endpoint", ""),
                input_values=payload.get("input_values", {}),
            )
        if operation == "rhino_command":
            return self.invoke_rhino_compute(
                endpoint=payload.get("endpoint", "/"),
                payload=payload.get("arguments", {}),
            )
        raise ValueError(f"Unsupported Rhino connector operation: {operation}")

    def evaluate_grasshopper_definition(
        self,
        definition_path: str,
        input_values: Optional[Dict[str, Any]] = None,
        pointer: Optional[str] = None,
    ) -> Dict[str, Any]:
        path = Path(definition_path)
        if not path.exists():
            raise FileNotFoundError(f"Grasshopper definition not found: {definition_path}")

        definition_data = base64.b64encode(path.read_bytes()).decode("utf-8")
        payload = {
            "algo": definition_data,
            "pointer": pointer,
            "values": self._format_grasshopper_values(input_values or {}),
        }
        result = self._request("POST", "/grasshopper", payload)
        return {
            "success": True,
            "definition_path": str(path),
            "pointer": pointer,
            "result": result,
        }

    def call_grasshopper_hops(
        self,
        endpoint: str,
        input_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not endpoint:
            raise ValueError("Grasshopper Hops endpoint is required")
        result = self._request("POST", endpoint, input_values or {})
        return {
            "success": True,
            "endpoint": endpoint,
            "result": result,
        }

    def invoke_rhino_compute(self, endpoint: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        result = self._request("POST", endpoint, payload or {})
        return {
            "success": True,
            "endpoint": endpoint,
            "result": result,
        }

    def _format_grasshopper_values(self, input_values: Dict[str, Any]) -> Any:
        formatted = []
        for key, value in input_values.items():
            inner_value = value if isinstance(value, list) else [value]
            formatted.append(
                {
                    "ParamName": key,
                    "InnerTree": {
                        "{0}": [{"type": self._infer_grasshopper_type(item), "data": json.dumps(item)} for item in inner_value]
                    },
                }
            )
        return formatted

    def _infer_grasshopper_type(self, value: Any) -> str:
        if isinstance(value, bool):
            return "System.Boolean"
        if isinstance(value, int):
            return "System.Int32"
        if isinstance(value, float):
            return "System.Double"
        if isinstance(value, dict):
            return "Rhino.Geometry.Point3d" if {"x", "y", "z"}.issubset(value.keys()) else "System.String"
        return "System.String"

    def _request(self, method: str, endpoint: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        endpoint = endpoint or "/"
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            url = endpoint
        else:
            url = self.config["base_url"].rstrip("/") + "/" + endpoint.lstrip("/")

        headers = {"Content-Type": "application/json"}
        if self.config.get("api_key"):
            headers["RhinoComputeKey"] = self.config["api_key"]

        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(url=url, data=data, headers=headers, method=method.upper())
        timeout = int(self.config.get("timeout", 120))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                try:
                    return json.loads(body) if body else {}
                except json.JSONDecodeError:
                    return {"raw": body}
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Rhino.Compute request failed: {exc.code} {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Rhino.Compute connection failed: {exc}") from exc
