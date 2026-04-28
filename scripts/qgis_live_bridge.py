"""UrbanAgent live bridge for QGIS.

Run this file inside QGIS with:
    qgis-ltr-bin.exe --code scripts/qgis_live_bridge.py

It exposes a small localhost HTTP API for UrbanAgent:
    GET  /status
    POST /commands
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading

from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer
from qgis.utils import iface


HOST = "127.0.0.1"
PORT = 8766


def _canvas_state() -> dict:
    canvas = iface.mapCanvas()
    center = canvas.center()
    return {
        "scale": canvas.scale(),
        "center": [center.x(), center.y()],
        "layer_count": len(QgsProject.instance().mapLayers()),
    }


class UrbanAgentQgisBridge(BaseHTTPRequestHandler):
    server_version = "UrbanAgentQGISBridge/0.1"

    def log_message(self, format, *args):
        return

    def _json(self, payload, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self._json({"ok": True})

    def do_GET(self):
        if self.path.rstrip("/") == "/status":
            self._json({
                "connected": True,
                "application": "QGIS",
                "bridge": "urban-agent-live-bridge",
                "project_title": QgsProject.instance().title(),
                "project_file": QgsProject.instance().fileName(),
                "canvas": _canvas_state(),
            })
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.rstrip("/") != "/commands":
            self._json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        executed = []
        errors = []
        for command in payload.get("commands", []):
            action = command.get("action")
            data = command.get("payload", {})
            try:
                _execute_command(action, data)
                executed.append(action)
            except Exception as error:
                errors.append({"action": action, "error": str(error)})
        self._json({"executed": executed, "errors": errors, "canvas": _canvas_state()})


def _execute_command(action, data):
    project = QgsProject.instance()
    if action == "set_project_title":
        project.setTitle(data.get("title", "UrbanAgent Live Session"))
    elif action == "add_vector_layer":
        layer = QgsVectorLayer(data.get("path", ""), data.get("name", "UrbanAgent vector"), "ogr")
        if not layer.isValid():
            raise RuntimeError(f"Invalid vector layer: {data.get('path', '')}")
        project.addMapLayer(layer)
    elif action == "add_raster_layer":
        layer = QgsRasterLayer(data.get("path", ""), data.get("name", "UrbanAgent raster"))
        if not layer.isValid():
            raise RuntimeError(f"Invalid raster layer: {data.get('path', '')}")
        project.addMapLayer(layer)
    elif action == "zoom_to_full_extent":
        iface.mapCanvas().zoomToFullExtent()
    elif action == "refresh_canvas":
        iface.mapCanvas().refresh()
    else:
        raise RuntimeError(f"Unsupported action: {action}")


def start_bridge():
    global URBAN_AGENT_QGIS_BRIDGE_SERVER
    try:
        URBAN_AGENT_QGIS_BRIDGE_SERVER.shutdown()
    except Exception:
        pass
    URBAN_AGENT_QGIS_BRIDGE_SERVER = HTTPServer((HOST, PORT), UrbanAgentQgisBridge)
    thread = threading.Thread(target=URBAN_AGENT_QGIS_BRIDGE_SERVER.serve_forever, daemon=True)
    thread.start()
    print(f"UrbanAgent QGIS bridge running at http://{HOST}:{PORT}")


start_bridge()