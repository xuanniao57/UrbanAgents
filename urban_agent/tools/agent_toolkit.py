"""General agent tool surface for UrbanAgent.

This module adopts the useful part of Hermes-style tool management: tool names
are grouped into explicit toolsets, categorized for governance, and routed
through one runtime. Tools that can be implemented safely with the standard
library do real work; tools that need external UI, gateway, browser, audio, or
smart-home backends return structured enablement requests instead of pretending
to execute.
"""

from __future__ import annotations

import json
import importlib
import os
import platform
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen


HERMES_CORE_TOOL_NAMES: tuple[str, ...] = (
    "web_search", "web_extract",
    "terminal", "process",
    "read_file", "write_file", "patch", "search_files",
    "vision_analyze", "image_generate",
    "skills_list", "skill_view", "skill_manage",
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_scroll", "browser_back",
    "browser_press", "browser_get_images",
    "browser_vision", "browser_console", "browser_cdp", "browser_dialog",
    "text_to_speech",
    "todo", "memory",
    "session_search",
    "clarify",
    "execute_code", "delegate_task",
    "cronjob",
    "send_message",
    "ha_list_entities", "ha_get_state", "ha_list_services", "ha_call_service",
    "kanban_show", "kanban_complete", "kanban_block", "kanban_heartbeat",
    "kanban_comment", "kanban_create", "kanban_link",
)


HERMES_TOOLSETS: Dict[str, tuple[str, ...]] = {
    "web": ("web_search", "web_extract"),
    "terminal": ("terminal", "process"),
    "file": ("read_file", "write_file", "patch", "search_files"),
    "vision": ("vision_analyze",),
    "image_gen": ("image_generate",),
    "skills": ("skills_list", "skill_view", "skill_manage"),
    "browser": (
        "browser_navigate", "browser_snapshot", "browser_click",
        "browser_type", "browser_scroll", "browser_back",
        "browser_press", "browser_get_images", "browser_vision",
        "browser_console", "browser_cdp", "browser_dialog", "web_search",
    ),
    "planning_memory": ("todo", "memory", "session_search", "clarify"),
    "execution_delegation": ("execute_code", "delegate_task"),
    "cronjob": ("cronjob",),
    "messaging": ("send_message",),
    "homeassistant": ("ha_list_entities", "ha_get_state", "ha_list_services", "ha_call_service"),
    "kanban": (
        "kanban_show", "kanban_complete", "kanban_block", "kanban_heartbeat",
        "kanban_comment", "kanban_create", "kanban_link",
    ),
    "hermes-cli": HERMES_CORE_TOOL_NAMES,
}

AGENT_CORE_TOOL_NAMES = HERMES_CORE_TOOL_NAMES
AGENT_TOOLSETS: Dict[str, tuple[str, ...]] = {
    **HERMES_TOOLSETS,
    "agent-core": AGENT_CORE_TOOL_NAMES,
}


DATA_UNDERSTANDING_TOOLS = {
    "web_search", "web_extract", "read_file", "search_files",
    "vision_analyze", "browser_snapshot", "browser_get_images", "browser_vision",
    "browser_console", "skills_list", "skill_view", "memory", "session_search",
}

DOMAIN_KNOWLEDGE_TOOLS = {
    "todo", "clarify", "delegate_task", "kanban_show", "kanban_comment", "kanban_link",
}


_TOOL_DESCRIPTIONS: Dict[str, str] = {
    "web_search": "Search the web or produce a search request for online urban research.",
    "web_extract": "Fetch and extract readable text from a web page URL.",
    "terminal": "Run or stage local terminal commands with explicit enablement.",
    "process": "Inspect or manage local process state with explicit enablement for destructive actions.",
    "read_file": "Read a bounded text file range from the workspace.",
    "write_file": "Write a workspace file when file-write tools are explicitly enabled.",
    "patch": "Apply a simple exact text replacement patch when file-write tools are enabled.",
    "search_files": "Search workspace filenames and optionally text contents.",
    "vision_analyze": "Inspect local image metadata or request a configured vision backend.",
    "image_generate": "Create an image-generation request for a configured backend.",
    "skills_list": "List available skill documents.",
    "skill_view": "Read a selected skill document.",
    "skill_manage": "Create or update skill documents when skill management is enabled.",
    "browser_navigate": "Record or request browser navigation.",
    "browser_snapshot": "Return the current browser-state snapshot or fetched page text.",
    "browser_click": "Record or request a browser click action.",
    "browser_type": "Record or request browser text entry.",
    "browser_scroll": "Record or request browser scrolling.",
    "browser_back": "Record or request browser back navigation.",
    "browser_press": "Record or request a browser key press.",
    "browser_get_images": "Extract image URLs from the current or supplied page URL.",
    "browser_vision": "Request visual inspection of a browser page.",
    "browser_console": "Return recorded browser-console notes.",
    "browser_cdp": "Create a Chrome DevTools Protocol request for a browser backend.",
    "browser_dialog": "Record a browser dialog response request.",
    "text_to_speech": "Create a text-to-speech request for a configured audio backend.",
    "todo": "Maintain an in-session todo list.",
    "memory": "Maintain lightweight in-session memory notes.",
    "session_search": "Search lightweight session memory, todos, and coordination notes.",
    "clarify": "Create a structured human clarification checkpoint.",
    "execute_code": "Execute or stage short Python code with explicit enablement.",
    "delegate_task": "Create an isolated subtask delegation request.",
    "cronjob": "Maintain in-session scheduled task definitions.",
    "send_message": "Create a gateway messaging request.",
    "ha_list_entities": "List Home Assistant entities when a backend is configured.",
    "ha_get_state": "Get Home Assistant entity state when configured.",
    "ha_list_services": "List Home Assistant services when configured.",
    "ha_call_service": "Call a Home Assistant service when configured.",
    "kanban_show": "Show the in-session kanban board.",
    "kanban_complete": "Mark a kanban task complete.",
    "kanban_block": "Mark a kanban task blocked.",
    "kanban_heartbeat": "Record progress heartbeat for a kanban task.",
    "kanban_comment": "Add a kanban task comment.",
    "kanban_create": "Create a kanban task.",
    "kanban_link": "Link two kanban tasks.",
}


@dataclass(frozen=True)
class HermesToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    category: str


def _tool_names_for(toolsets: Optional[Sequence[str]] = None) -> tuple[str, ...]:
    if not toolsets:
        return AGENT_CORE_TOOL_NAMES
    selected: list[str] = []
    for item in toolsets:
        if item in AGENT_TOOLSETS:
            selected.extend(AGENT_TOOLSETS[item])
        elif item in AGENT_CORE_TOOL_NAMES:
            selected.append(item)
    return tuple(dict.fromkeys(selected))


def get_hermes_tool_specs(toolsets: Optional[Sequence[str]] = None) -> List[HermesToolSpec]:
    return [
        HermesToolSpec(
            name=name,
            description=_TOOL_DESCRIPTIONS[name],
            parameters=_parameters_for(name),
            category=hermes_tool_category(name),
        )
        for name in _tool_names_for(toolsets)
    ]


AgentToolSpec = HermesToolSpec


def get_agent_tool_specs(toolsets: Optional[Sequence[str]] = None) -> List[AgentToolSpec]:
    return get_hermes_tool_specs(toolsets)


def hermes_tool_category(name: str) -> str:
    if name in DATA_UNDERSTANDING_TOOLS:
        return "Data Understanding"
    if name in DOMAIN_KNOWLEDGE_TOOLS:
        return "Domain Knowledge"
    return "System Interaction"


def agent_tool_category(name: str) -> str:
    return hermes_tool_category(name)


def register_hermes_core_tools(register_tool: Callable[..., None], toolsets: Optional[Sequence[str]] = None) -> "HermesToolRuntime":
    runtime = HermesToolRuntime()
    for spec in get_hermes_tool_specs(toolsets):
        register_tool(
            name=spec.name,
            description=spec.description,
            parameters=spec.parameters,
            handler=runtime.handler_for(spec.name),
        )
    return runtime


def register_agent_core_tools(register_tool: Callable[..., None], toolsets: Optional[Sequence[str]] = None) -> "HermesToolRuntime":
    return register_hermes_core_tools(register_tool, toolsets=toolsets)


def register_agent_tool_manifest(register_tool: Callable[..., None], manifest_path: str | Path) -> list[str]:
    """Register user-provided tools from a small JSON manifest.

    Each item needs name, description, parameters, and a python_function target
    in the form ``package.module:function``. This keeps custom tools outside
    the UrbanAgent kernel while preserving the same runtime dispatch surface.
    """

    path = Path(manifest_path).expanduser().resolve()
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    items = data.get("tools", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("tool manifest must be a list or contain a 'tools' list")

    registered: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        target = str(item.get("python_function") or item.get("handler") or "").strip()
        if not name or not target:
            continue
        handler = _import_python_handler(target)
        register_tool(
            name=name,
            description=str(item.get("description") or name),
            parameters=item.get("parameters") or _schema({}, []),
            handler=handler,
        )
        registered.append(name)
    return registered


class HermesToolRuntime:
    def __init__(self) -> None:
        self.todos: list[dict[str, Any]] = []
        self.memory: dict[str, Any] = {}
        self.kanban: dict[str, dict[str, Any]] = {}
        self.cronjobs: dict[str, dict[str, Any]] = {}
        self.browser_state: dict[str, Any] = {"url": None, "history": [], "events": [], "console": []}
        self.messages: list[dict[str, Any]] = []

    def handler_for(self, tool_name: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
        handlers = {
            "web_search": self._handle_web_search,
            "web_extract": self._handle_web_extract,
            "terminal": self._handle_terminal,
            "process": self._handle_process,
            "read_file": self._handle_read_file,
            "write_file": self._handle_write_file,
            "patch": self._handle_patch,
            "search_files": self._handle_search_files,
            "vision_analyze": self._handle_vision_analyze,
            "image_generate": self._handle_image_generate,
            "skills_list": self._handle_skills_list,
            "skill_view": self._handle_skill_view,
            "skill_manage": self._handle_skill_manage,
            "text_to_speech": self._handle_text_to_speech,
            "todo": self._handle_todo,
            "memory": self._handle_memory,
            "session_search": self._handle_session_search,
            "clarify": self._handle_clarify,
            "execute_code": self._handle_execute_code,
            "delegate_task": self._handle_delegate_task,
            "cronjob": self._handle_cronjob,
            "send_message": self._handle_send_message,
            "ha_list_entities": self._handle_homeassistant,
            "ha_get_state": self._handle_homeassistant,
            "ha_list_services": self._handle_homeassistant,
            "ha_call_service": self._handle_homeassistant,
            "kanban_show": self._handle_kanban_show,
            "kanban_complete": self._handle_kanban_complete,
            "kanban_block": self._handle_kanban_block,
            "kanban_heartbeat": self._handle_kanban_heartbeat,
            "kanban_comment": self._handle_kanban_comment,
            "kanban_create": self._handle_kanban_create,
            "kanban_link": self._handle_kanban_link,
        }
        if tool_name.startswith("browser_"):
            return lambda args: self._handle_browser(tool_name, args)
        return handlers.get(tool_name, self._handle_unavailable)

    def _handle_web_search(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query") or args.get("q") or "").strip()
        if not query:
            raise ValueError("query is required")
        search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        if str(args.get("fetch") or "").lower() in {"1", "true", "yes"}:
            return self._extract_url(search_url, max_chars=int(args.get("max_chars", 4000))) | {"query": query, "search_url": search_url}
        return {"query": query, "search_url": search_url, "status": "ready_for_external_search"}

    def _handle_web_extract(self, args: Dict[str, Any]) -> Dict[str, Any]:
        url = str(args.get("url") or "").strip()
        if not url:
            raise ValueError("url is required")
        return self._extract_url(url, max_chars=int(args.get("max_chars", 12000)))

    def _handle_terminal(self, args: Dict[str, Any]) -> Dict[str, Any]:
        command = str(args.get("command") or "").strip()
        if not command:
            raise ValueError("command is required")
        cwd = str(args.get("cwd") or _workspace_root())
        timeout = min(int(args.get("timeout", 60)), int(os.getenv("URBAN_AGENT_TERMINAL_MAX_TIMEOUT", "120")))
        execute = bool(args.get("execute")) or str(args.get("mode") or "").lower() == "execute"
        if not execute or os.getenv("URBAN_AGENT_ENABLE_TERMINAL_TOOL") != "1":
            return {"command": command, "cwd": cwd, "dry_run": True, "enable_with": "URBAN_AGENT_ENABLE_TERMINAL_TOOL=1"}
        completed = subprocess.run(command, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {
            "command": command,
            "cwd": cwd,
            "returncode": completed.returncode,
            "stdout": _truncate(completed.stdout),
            "stderr": _truncate(completed.stderr),
        }

    def _handle_process(self, args: Dict[str, Any]) -> Dict[str, Any]:
        action = str(args.get("action") or "list").lower()
        if action == "list":
            command = "tasklist" if platform.system().lower().startswith("win") else "ps -eo pid,comm,args"
            completed = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
            return {"action": action, "returncode": completed.returncode, "output": _truncate(completed.stdout, 12000)}
        if os.getenv("URBAN_AGENT_ENABLE_PROCESS_CONTROL") != "1":
            return {"action": action, "dry_run": True, "enable_with": "URBAN_AGENT_ENABLE_PROCESS_CONTROL=1"}
        return {"action": action, "status": "process control action acknowledged", "arguments": dict(args)}

    def _handle_read_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = _safe_path(str(args.get("path") or args.get("file_path") or ""))
        start = max(int(args.get("start_line", 1)), 1)
        max_lines = max(int(args.get("max_lines", args.get("limit", 200))), 1)
        lines = path.read_text(encoding=args.get("encoding") or "utf-8", errors="replace").splitlines()
        selected = lines[start - 1:start - 1 + max_lines]
        return {"path": str(path), "start_line": start, "line_count": len(selected), "total_lines": len(lines), "text": "\n".join(selected)}

    def _handle_write_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = _safe_path(str(args.get("path") or args.get("file_path") or ""), must_exist=False)
        content = str(args.get("content") or "")
        if os.getenv("URBAN_AGENT_ENABLE_FILE_WRITE_TOOLS") != "1":
            return {"path": str(path), "bytes": len(content.encode("utf-8")), "dry_run": True, "enable_with": "URBAN_AGENT_ENABLE_FILE_WRITE_TOOLS=1"}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=args.get("encoding") or "utf-8")
        return {"path": str(path), "bytes": len(content.encode("utf-8")), "written": True}

    def _handle_patch(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = _safe_path(str(args.get("path") or args.get("file_path") or ""))
        old_text = str(args.get("old_text") or "")
        new_text = str(args.get("new_text") or "")
        if not old_text:
            raise ValueError("old_text is required")
        text = path.read_text(encoding=args.get("encoding") or "utf-8", errors="replace")
        occurrences = text.count(old_text)
        if occurrences != 1:
            return {"path": str(path), "matched": occurrences, "patched": False, "error": "old_text must appear exactly once"}
        if os.getenv("URBAN_AGENT_ENABLE_FILE_WRITE_TOOLS") != "1":
            return {"path": str(path), "matched": occurrences, "dry_run": True, "enable_with": "URBAN_AGENT_ENABLE_FILE_WRITE_TOOLS=1"}
        path.write_text(text.replace(old_text, new_text), encoding=args.get("encoding") or "utf-8")
        return {"path": str(path), "matched": occurrences, "patched": True}

    def _handle_search_files(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        root = _safe_path(str(args.get("path") or "."), must_exist=True)
        include_content = bool(args.get("include_content"))
        use_regex = bool(args.get("regex"))
        limit = int(args.get("limit", 50))
        matcher = re.compile(query, re.IGNORECASE) if use_regex else None
        matches: list[dict[str, Any]] = []
        paths = [root] if root.is_file() else (item for item in root.rglob("*") if item.is_file())
        for item in paths:
            rel = str(item)
            name_hit = bool(matcher.search(rel) if matcher else query.lower() in rel.lower())
            content_hit = False
            snippet = ""
            if include_content and _looks_textual(item):
                text = item.read_text(encoding="utf-8", errors="replace")[:200000]
                content_hit = bool(matcher.search(text) if matcher else query.lower() in text.lower())
                if content_hit:
                    snippet = _snippet(text, matcher.search(text).start() if matcher else text.lower().find(query.lower()))
            if name_hit or content_hit:
                matches.append({"path": str(item), "name_hit": name_hit, "content_hit": content_hit, "snippet": snippet})
            if len(matches) >= limit:
                break
        return {"query": query, "root": str(root), "matches": matches, "truncated": len(matches) >= limit}

    def _handle_vision_analyze(self, args: Dict[str, Any]) -> Dict[str, Any]:
        image_path = args.get("image_path") or args.get("path")
        if not image_path:
            return _requires_backend("vision backend", "Provide image_path for local metadata or configure a VLM backend.")
        path = _safe_path(str(image_path))
        result: dict[str, Any] = {"path": str(path), "bytes": path.stat().st_size}
        try:
            from PIL import Image
            with Image.open(path) as image:
                result.update({"width": image.width, "height": image.height, "mode": image.mode, "format": image.format})
        except Exception as exc:
            result["metadata_note"] = str(exc)
        return result

    def _handle_image_generate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "image_generation_request_created", "prompt": args.get("prompt"), "requires_backend": "configured image generation provider"}

    def _handle_skills_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        skills = []
        for root in _skill_roots():
            if not root.exists():
                continue
            for skill_file in root.glob("*/SKILL.md"):
                skills.append({"name": skill_file.parent.name, "path": str(skill_file)})
        return {"skills": sorted(skills, key=lambda item: item["name"])}

    def _handle_skill_view(self, args: Dict[str, Any]) -> Dict[str, Any]:
        name = str(args.get("name") or args.get("skill") or "").strip()
        if not name:
            raise ValueError("name is required")
        for root in _skill_roots():
            path = root / name / "SKILL.md"
            if path.exists():
                return {"name": name, "path": str(path), "text": path.read_text(encoding="utf-8", errors="replace")}
        raise FileNotFoundError(f"skill not found: {name}")

    def _handle_skill_manage(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if os.getenv("URBAN_AGENT_ENABLE_SKILL_MANAGEMENT") != "1":
            return {"dry_run": True, "enable_with": "URBAN_AGENT_ENABLE_SKILL_MANAGEMENT=1", "request": dict(args)}
        return {"status": "skill management backend not implemented in this runtime", "request": dict(args)}

    def _handle_browser(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        event = {"tool": tool_name, "args": dict(args), "timestamp": time.time()}
        self.browser_state["events"].append(event)
        if tool_name == "browser_navigate":
            url = str(args.get("url") or "")
            if url:
                if self.browser_state.get("url"):
                    self.browser_state["history"].append(self.browser_state["url"])
                self.browser_state["url"] = url
            return {"browser_state": dict(self.browser_state), "requires_backend": "browser automation backend for live navigation"}
        if tool_name == "browser_back":
            if self.browser_state["history"]:
                self.browser_state["url"] = self.browser_state["history"].pop()
            return {"browser_state": dict(self.browser_state)}
        if tool_name == "browser_snapshot" and self.browser_state.get("url"):
            extracted = self._extract_url(str(self.browser_state["url"]), max_chars=int(args.get("max_chars", 6000)))
            return {"browser_state": dict(self.browser_state), "snapshot": extracted}
        if tool_name == "browser_get_images":
            url = str(args.get("url") or self.browser_state.get("url") or "")
            if not url:
                return {"images": [], "requires_url": True}
            text = self._fetch_text(url, max_chars=200000)
            images = re.findall(r"<img[^>]+src=[\"']([^\"']+)[\"']", text, flags=re.I)
            return {"url": url, "images": images[: int(args.get("limit", 50))]}
        if tool_name == "browser_console":
            return {"console": list(self.browser_state.get("console", [])), "requires_backend": "browser automation backend for live console logs"}
        return {"browser_event": event, "requires_backend": "browser automation backend"}

    def _handle_text_to_speech(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "tts_request_created", "text_chars": len(str(args.get("text") or "")), "requires_backend": "configured TTS provider"}

    def _handle_todo(self, args: Dict[str, Any]) -> Dict[str, Any]:
        action = str(args.get("action") or "list").lower()
        if action in {"add", "create"}:
            item = {"id": str(args.get("id") or uuid.uuid4().hex[:8]), "title": str(args.get("title") or args.get("task") or "untitled"), "status": str(args.get("status") or "pending")}
            self.todos.append(item)
            return {"todo": item, "todos": list(self.todos)}
        if action in {"update", "complete", "block"}:
            item_id = str(args.get("id") or "")
            status = "completed" if action == "complete" else "blocked" if action == "block" else str(args.get("status") or "pending")
            for item in self.todos:
                if item["id"] == item_id or item["title"] == item_id:
                    item["status"] = status
                    return {"todo": item, "todos": list(self.todos)}
            raise KeyError(f"todo not found: {item_id}")
        if action == "clear":
            self.todos.clear()
        return {"todos": list(self.todos)}

    def _handle_memory(self, args: Dict[str, Any]) -> Dict[str, Any]:
        action = str(args.get("action") or "list").lower()
        key = str(args.get("key") or "").strip()
        if action in {"set", "create", "update"}:
            if not key:
                raise ValueError("key is required")
            self.memory[key] = args.get("value")
        elif action == "delete" and key:
            self.memory.pop(key, None)
        elif action == "get" and key:
            return {"key": key, "value": self.memory.get(key)}
        return {"memory": dict(self.memory)}

    def _handle_session_search(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query") or "").lower()
        haystack = {
            "todos": self.todos,
            "memory": self.memory,
            "kanban": self.kanban,
            "cronjobs": self.cronjobs,
            "messages": self.messages,
        }
        text = json.dumps(haystack, ensure_ascii=False, default=str)
        index = text.lower().find(query) if query else -1
        return {"query": query, "matched": index >= 0, "snippet": _snippet(text, index) if index >= 0 else ""}

    def _handle_clarify(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"checkpoint": "clarification_required", "question": args.get("question"), "options": args.get("options", []), "context": args.get("context", {})}

    def _handle_execute_code(self, args: Dict[str, Any]) -> Dict[str, Any]:
        code = str(args.get("code") or "")
        if not code:
            raise ValueError("code is required")
        if os.getenv("URBAN_AGENT_ENABLE_CODE_EXECUTION_TOOL") != "1":
            return {"code_chars": len(code), "dry_run": True, "enable_with": "URBAN_AGENT_ENABLE_CODE_EXECUTION_TOOL=1"}
        completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=min(int(args.get("timeout", 30)), 120))
        return {"returncode": completed.returncode, "stdout": _truncate(completed.stdout), "stderr": _truncate(completed.stderr)}

    def _handle_delegate_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"delegation_id": uuid.uuid4().hex[:12], "status": "delegation_request_created", "task": args.get("task"), "context": args.get("context", {})}

    def _handle_cronjob(self, args: Dict[str, Any]) -> Dict[str, Any]:
        action = str(args.get("action") or "list").lower()
        if action in {"create", "add"}:
            job_id = str(args.get("id") or uuid.uuid4().hex[:8])
            self.cronjobs[job_id] = {"id": job_id, "schedule": args.get("schedule"), "task": args.get("task"), "status": "active"}
        elif action in {"pause", "resume", "remove"}:
            job_id = str(args.get("id") or "")
            if action == "remove":
                self.cronjobs.pop(job_id, None)
            elif job_id in self.cronjobs:
                self.cronjobs[job_id]["status"] = "paused" if action == "pause" else "active"
        return {"cronjobs": dict(self.cronjobs)}

    def _handle_send_message(self, args: Dict[str, Any]) -> Dict[str, Any]:
        message = {"channel": args.get("channel"), "recipient": args.get("recipient"), "text": args.get("text"), "timestamp": time.time()}
        self.messages.append(message)
        return {"message": message, "requires_backend": "Hermes gateway or configured messaging adapter"}

    def _handle_homeassistant(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not os.getenv("HASS_TOKEN") or not os.getenv("HASS_URL"):
            return _requires_backend("Home Assistant", "Set HASS_URL and HASS_TOKEN to enable Home Assistant tools.")
        return {"status": "homeassistant_request_created", "request": dict(args)}

    def _handle_kanban_show(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"kanban": dict(self.kanban)}

    def _handle_kanban_create(self, args: Dict[str, Any]) -> Dict[str, Any]:
        task_id = str(args.get("id") or uuid.uuid4().hex[:8])
        self.kanban[task_id] = {"id": task_id, "title": args.get("title") or args.get("task") or "untitled", "status": "open", "comments": [], "links": []}
        return {"task": self.kanban[task_id], "kanban": dict(self.kanban)}

    def _handle_kanban_complete(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return self._update_kanban(args, "completed")

    def _handle_kanban_block(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return self._update_kanban(args, "blocked")

    def _handle_kanban_heartbeat(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return self._kanban_comment(args, heartbeat=True)

    def _handle_kanban_comment(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return self._kanban_comment(args, heartbeat=False)

    def _handle_kanban_link(self, args: Dict[str, Any]) -> Dict[str, Any]:
        source = str(args.get("source") or args.get("id") or "")
        target = str(args.get("target") or "")
        self.kanban.setdefault(source, {"id": source, "title": source, "status": "open", "comments": [], "links": []})["links"].append(target)
        return {"task": self.kanban[source], "kanban": dict(self.kanban)}

    def _update_kanban(self, args: Dict[str, Any], status: str) -> Dict[str, Any]:
        task_id = str(args.get("id") or "")
        self.kanban.setdefault(task_id, {"id": task_id, "title": task_id, "status": "open", "comments": [], "links": []})["status"] = status
        return {"task": self.kanban[task_id], "kanban": dict(self.kanban)}

    def _kanban_comment(self, args: Dict[str, Any], *, heartbeat: bool) -> Dict[str, Any]:
        task_id = str(args.get("id") or "")
        item = self.kanban.setdefault(task_id, {"id": task_id, "title": task_id, "status": "open", "comments": [], "links": []})
        item["comments"].append({"text": args.get("comment") or args.get("message") or "", "heartbeat": heartbeat, "timestamp": time.time()})
        return {"task": item, "kanban": dict(self.kanban)}

    def _handle_unavailable(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "unavailable", "request": dict(args)}

    def _extract_url(self, url: str, *, max_chars: int) -> Dict[str, Any]:
        html = self._fetch_text(url, max_chars=max(max_chars * 4, 20000))
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
        text = _html_to_text(html)
        return {"url": url, "title": _collapse(title_match.group(1)) if title_match else "", "text": _truncate(text, max_chars)}

    @staticmethod
    def _fetch_text(url: str, *, max_chars: int) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http(s) URLs are supported")
        request = Request(url, headers={"User-Agent": "UrbanAgent/0.1 HermesToolkit"})
        with urlopen(request, timeout=20) as response:
            raw = response.read(max_chars).decode("utf-8", errors="replace")
        return raw


def _parameters_for(name: str) -> Dict[str, Any]:
    common = {"type": "object", "properties": {}, "additionalProperties": True}
    schemas: Dict[str, Dict[str, Any]] = {
        "web_search": _schema({"query": "string", "fetch": "boolean", "max_chars": "integer"}, ["query"]),
        "web_extract": _schema({"url": "string", "max_chars": "integer"}, ["url"]),
        "terminal": _schema({"command": "string", "cwd": "string", "timeout": "integer", "execute": "boolean", "mode": "string"}, ["command"]),
        "process": _schema({"action": "string", "pid": "string"}),
        "read_file": _schema({"path": "string", "start_line": "integer", "max_lines": "integer", "encoding": "string"}, ["path"]),
        "write_file": _schema({"path": "string", "content": "string", "encoding": "string"}, ["path", "content"]),
        "patch": _schema({"path": "string", "old_text": "string", "new_text": "string", "encoding": "string"}, ["path", "old_text", "new_text"]),
        "search_files": _schema({"query": "string", "path": "string", "include_content": "boolean", "regex": "boolean", "limit": "integer"}, ["query"]),
        "vision_analyze": _schema({"image_path": "string", "question": "string"}),
        "image_generate": _schema({"prompt": "string", "style": "string"}, ["prompt"]),
        "skills_list": _schema({"root": "string"}),
        "skill_view": _schema({"name": "string"}, ["name"]),
        "skill_manage": _schema({"action": "string", "name": "string", "content": "string"}),
        "todo": _schema({"action": "string", "id": "string", "title": "string", "status": "string"}),
        "memory": _schema({"action": "string", "key": "string", "value": "object"}),
        "session_search": _schema({"query": "string"}, ["query"]),
        "clarify": _schema({"question": "string", "options": "array", "context": "object"}, ["question"]),
        "execute_code": _schema({"code": "string", "timeout": "integer"}, ["code"]),
        "delegate_task": _schema({"task": "string", "context": "object"}, ["task"]),
        "cronjob": _schema({"action": "string", "id": "string", "schedule": "string", "task": "string"}),
        "send_message": _schema({"channel": "string", "recipient": "string", "text": "string"}, ["text"]),
        "text_to_speech": _schema({"text": "string", "voice": "string"}, ["text"]),
    }
    if name.startswith("browser_"):
        return _schema({"url": "string", "selector": "string", "text": "string", "key": "string", "max_chars": "integer"})
    if name.startswith("ha_"):
        return _schema({"entity_id": "string", "domain": "string", "service": "string", "data": "object"})
    if name.startswith("kanban_"):
        return _schema({"id": "string", "title": "string", "task": "string", "comment": "string", "message": "string", "source": "string", "target": "string"})
    return schemas.get(name, common)


def _schema(properties: Dict[str, str], required: Optional[list[str]] = None) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {key: {"type": value} for key, value in properties.items()},
        "required": required or [],
        "additionalProperties": True,
    }


def _workspace_root() -> Path:
    return Path(os.getenv("URBAN_AGENT_TOOL_ROOT", os.getcwd())).expanduser().resolve()


def _safe_path(path_value: str, *, must_exist: bool = True) -> Path:
    if not path_value:
        raise ValueError("path is required")
    root = _workspace_root()
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    if os.getenv("URBAN_AGENT_ALLOW_OUTSIDE_TOOL_ROOT") != "1" and root not in (resolved, *resolved.parents):
        raise ValueError(f"path is outside tool root: {resolved}")
    if must_exist and not resolved.exists():
        raise FileNotFoundError(str(resolved))
    return resolved


def _skill_roots() -> list[Path]:
    roots = []
    for value in (os.getenv("URBAN_AGENT_SKILLS_DIR"), os.getenv("VSCODE_USER_PROMPTS_FOLDER")):
        if value:
            roots.append(Path(value).expanduser())
    roots.extend([Path.home() / ".claude" / "skills", _workspace_root() / "skills"])
    return [root.resolve() for root in roots]


def _looks_textual(path: Path) -> bool:
    return path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".7z", ".exe", ".dll"}


def _truncate(text: str, max_chars: int = 20000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]"


def _html_to_text(html: str) -> str:
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return _collapse(html)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _snippet(text: str, index: int, radius: int = 240) -> str:
    start = max(index - radius, 0)
    end = min(index + radius, len(text))
    return text[start:end]


def _requires_backend(name: str, message: str) -> Dict[str, Any]:
    return {"requires_backend": name, "message": message}


def _import_python_handler(target: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    module_name, _, function_name = target.partition(":")
    if not module_name or not function_name:
        raise ValueError(f"invalid python_function target: {target}")
    module = importlib.import_module(module_name)
    handler = getattr(module, function_name)
    if not callable(handler):
        raise TypeError(f"python_function is not callable: {target}")
    return handler


AgentToolRuntime = HermesToolRuntime


__all__ = [
    "AGENT_CORE_TOOL_NAMES",
    "AGENT_TOOLSETS",
    "AgentToolRuntime",
    "AgentToolSpec",
    "HERMES_CORE_TOOL_NAMES",
    "HERMES_TOOLSETS",
    "HermesToolRuntime",
    "HermesToolSpec",
    "agent_tool_category",
    "get_agent_tool_specs",
    "get_hermes_tool_specs",
    "hermes_tool_category",
    "register_agent_core_tools",
    "register_agent_tool_manifest",
    "register_hermes_core_tools",
]
