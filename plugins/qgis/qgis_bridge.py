"""HTTP bridge client for live QGIS control.

UrbanAgent cannot drive the QGIS desktop UI through ``qgis_process`` alone.
For real-time control, QGIS should run a small local bridge/plugin that accepts
HTTP JSON commands on localhost. This module keeps the production surface honest:
it detects whether that bridge is online, sends commands when available, and
returns an auditable pending queue when QGIS is not connected.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


DEFAULT_QGIS_BRIDGE_URL = "http://127.0.0.1:8766"


@dataclass
class QgisCommand:
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QgisBridgeClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 1.5):
        self.base_url = (base_url or os.getenv("URBAN_AGENT_QGIS_BRIDGE_URL") or DEFAULT_QGIS_BRIDGE_URL).rstrip("/")
        self.timeout = timeout

    def status(self) -> dict[str, Any]:
        try:
            payload = self._request("GET", "/status")
        except Exception as error:
            return {
                "connected": False,
                "base_url": self.base_url,
                "message": f"QGIS live bridge is not connected: {error}",
                "mode": "pending_queue",
            }
        if not isinstance(payload, dict):
            payload = {"raw": payload}
        payload.setdefault("connected", True)
        payload.setdefault("base_url", self.base_url)
        payload.setdefault("mode", "live")
        return payload

    def send_commands(self, commands: list[dict[str, Any]]) -> dict[str, Any]:
        status = self.status()
        if not status.get("connected"):
            return {
                "sent": False,
                "queued": commands,
                "status": status,
                "message": "QGIS bridge is offline; commands are queued for live replay.",
            }
        try:
            result = self._request("POST", "/commands", {"commands": commands})
        except Exception as error:
            return {
                "sent": False,
                "queued": commands,
                "status": status,
                "message": f"QGIS bridge command dispatch failed: {error}",
            }
        return {"sent": True, "queued": [], "status": status, "result": result}

    def _request(self, method: str, path: str, payload: Optional[dict[str, Any]] = None) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"HTTP {error.code}") from error
        return json.loads(body) if body else {}


def qgis_bridge_status() -> dict[str, Any]:
    return QgisBridgeClient().status()


def qgis_bridge_plugin_stub() -> str:
    return """
# UrbanAgent QGIS bridge stub
# Run inside QGIS Python console, or adapt into a QGIS plugin.
# It exposes http://127.0.0.1:8766/status and /commands for UrbanAgent.

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading

from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer
from qgis.utils import iface


class UrbanAgentBridgeHandler(BaseHTTPRequestHandler):
    def _json(self, payload, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        if self.path == '/status':
            self._json({'connected': True, 'application': 'QGIS', 'project': QgsProject.instance().fileName()})
        else:
            self._json({'error': 'not found'}, 404)

    def do_POST(self):
        if self.path != '/commands':
            self._json({'error': 'not found'}, 404)
            return
        length = int(self.headers.get('Content-Length', '0'))
        payload = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        executed = []
        for command in payload.get('commands', []):
            action = command.get('action')
            data = command.get('payload', {})
            if action == 'set_project_title':
                QgsProject.instance().setTitle(data.get('title', 'UrbanAgent Live Session'))
            elif action == 'add_vector_layer':
                layer = QgsVectorLayer(data.get('path', ''), data.get('name', 'UrbanAgent vector'), 'ogr')
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
            elif action == 'add_raster_layer':
                layer = QgsRasterLayer(data.get('path', ''), data.get('name', 'UrbanAgent raster'))
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
            elif action == 'zoom_to_full_extent':
                iface.mapCanvas().zoomToFullExtent()
            elif action == 'refresh_canvas':
                iface.mapCanvas().refresh()
            executed.append(action)
        self._json({'executed': executed})


server = HTTPServer(('127.0.0.1', 8766), UrbanAgentBridgeHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
print('UrbanAgent QGIS bridge running at http://127.0.0.1:8766')
""".strip()