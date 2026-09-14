"""Read-only source audit and blinded researcher transcripts for a long pilot.

Run from any directory; standard library only. Defaults to evaluation/long27_20260831.
    python scripts/summarize-long-pilot.py --out evaluation/long27_20260831_review
Re-running updates derived materials only. Share the review/ directory with judges,
NOT audit.json (which contains the unblinding key and original evidence locations).
No scoring, remote access, request-body/auth reading, protocol edits or source edits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(value) + "\n", encoding="utf-8")


def short(text, limit=1600):
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[… {len(text) - limit} characters omitted here; see linked complete evidence.]"


def blocks_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(str(block.get("text", "")) for block in content
                     if isinstance(block, dict) and block.get("type") == "text")


class Sources:
    def __init__(self, root):
        self.root, self.files, self.issues = root, {}, []

    def read(self, path, optional=False):
        if not path.exists():
            if not optional:
                self.issues.append({"source": str(path), "issue": "missing"})
            return None
        try:
            raw = path.read_bytes()
            self.files[str(path.relative_to(self.root))] = {"bytes": len(raw), "sha256": digest(raw)}
            return raw.decode("utf-8-sig")
        except (OSError, UnicodeError) as exc:
            self.issues.append({"source": str(path), "issue": str(exc)})
            return None

    def json(self, path, optional=False):
        text = self.read(path, optional)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            self.issues.append({"source": str(path), "issue": f"invalid/incomplete JSON: {exc}"})
            return None

    def jsonl(self, path, optional=False):
        text = self.read(path, optional)
        if text is None:
            return []
        rows = []
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append((number, value))
            except json.JSONDecodeError:
                self.issues.append({"source": str(path), "line": number,
                                    "issue": "invalid/incomplete JSONL line; not treated as complete evidence"})
        return rows


class Blind:
    """Remove condition identifiers and credential-shaped fields, not behavior."""
    def __init__(self, root, source, alias):
        self.root, self.source, self.alias = root, source, alias

    def text(self, text):
        text = str(text)
        for condition in ("urban_full", "pi_default_compaction", "pi_default", "hybrid_recall"):
            text = text.replace(condition, "[configuration]")
        # Both remote and local run paths are replaced; suffixes remain locatable.
        text = re.sub(r"(?:[A-Za-z]:[/\\]|/)[^\s\"'`<>\[\]{}。，；、：]*[/\\]evaluation[/\\]" + re.escape(self.root.name) + r"[/\\][AB](?=[/\\\s\"'`<>。，；、]|$)",
                      "[SESSION_ROOT]", text)
        text = text.replace(str(self.root / self.source), "[SESSION_ROOT]")
        text = text.replace((self.root / self.source).as_posix(), "[SESSION_ROOT]")
        text = re.sub(r"(?:[A-Za-z]:[/\\]|/)[^\s\"'`<>\[\]{}。，；、：]*[/\\]pi_urban_agent[/\\]long_case(?=[/\\\s\"'`<>。，；、]|$)",
                      "[TOOL_ROOT]", text)
        text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
        text = re.sub(r"\bsk-[A-Za-z0-9_-]{16,}\b", "[REDACTED_KEY]", text)
        text = re.sub(r"(?i)((?:api[_-]?key|authorization|password|secret)\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", text)
        return text

    def value(self, value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key.lower() in {"condition", "contextmode", "urban_context_mode", "conditionscope"}:
                    result[key] = "[configuration withheld]"
                elif key.lower().replace("_", "") in {"apikey", "authorization", "password", "secret", "accesstoken", "refreshtoken"}:
                    result[key] = "[REDACTED]"
                else:
                    result[key] = self.value(item)
            return result
        if isinstance(value, list):
            return [self.value(item) for item in value]
        return self.text(value) if isinstance(value, str) else value


def state_changes(before, after, pointer=""):
    """Complete structural diff; arrays remain intact to avoid invented matching."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            path = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
            if key not in before:
                result.append({"path": path, "change": "added", "after": after[key]})
            elif key not in after:
                result.append({"path": path, "change": "removed", "before": before[key]})
            else:
                result.extend(state_changes(before[key], after[key], path))
        return result
    return [{"path": pointer or "/", "change": "changed", "before": before, "after": after}]


def state_overview(value):
    if value is None:
        return {"initialized": False}
    if not isinstance(value, dict):
        return {"type": type(value).__name__}
    overview = {key: value.get(key) for key in ("stateVersion", "phase", "activeBranchId", "contractHash") if key in value}
    overview["initialized"] = True
    for key in ("nodes", "artifacts", "reviews", "humanDecisions", "pendingHumanPatches", "pendingQuestions"):
        if key in value:
            overview[key + "Count"] = len(value[key]) if isinstance(value[key], (dict, list)) else None
    if isinstance(value.get("nodes"), dict):
        overview["nodeStatusCounts"] = dict(Counter(str(n.get("status")) for n in value["nodes"].values() if isinstance(n, dict)))
    return overview


def event_time(event):
    timestamp = event.get("timestamp") or event.get("message", {}).get("timestamp")
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat()
    return event.get("time") or timestamp


def compact_events(events, timeline):
    """One entry per completed message/call; merge delta streams only as fallback."""
    tool_times = {(e.get("event"), e.get("toolCallId")): e.get("time") for _, e in timeline if e.get("toolCallId")}
    ui_resolutions = {e.get("requestId"): e for _, e in timeline if e.get("event") == "human_ui_cancelled"}
    rows, calls, pending, compactions = [], {}, None, []
    ignored_updates = 0

    def flush_pending(line):
        nonlocal pending
        if pending:
            text = "\n".join(pending["blocks"][key] for key in sorted(pending["blocks"]))
            if text:
                rows.append({"kind": "assistant_partial", "text": text, "event_line": pending["line"],
                             "event_end_line": line, "time": pending["time"], "incomplete": True})
            pending = None

    for line, event in events:
        kind = event.get("type", "")
        if kind == "message_start" and event.get("message", {}).get("role") == "assistant":
            flush_pending(line - 1)
            pending = {"blocks": {}, "line": line, "time": event_time(event)}
        elif kind == "message_update":
            ignored_updates += 1
            delta = event.get("assistantMessageEvent", {})
            if delta.get("type") == "text_delta":
                if pending is None:
                    pending = {"blocks": {}, "line": line, "time": event_time(event)}
                index = delta.get("contentIndex", 0)
                pending["blocks"][index] = pending["blocks"].get(index, "") + str(delta.get("delta", ""))
        elif kind == "message_end":
            message = event.get("message", {})
            if message.get("role") == "assistant":
                text = blocks_text(message.get("content"))
                # message_end is authoritative; do not duplicate its streaming text.
                pending = None
                if text or message.get("errorMessage"):
                    rows.append({"kind": "assistant", "text": text, "event_line": line,
                                 "time": event_time(event), "stop_reason": message.get("stopReason"),
                                 "error": message.get("errorMessage")})
        elif kind == "tool_execution_start":
            call = {"kind": "tool", "tool": event.get("toolName"), "call_id": event.get("toolCallId"),
                    "arguments": event.get("args", {}), "event_line": line,
                    "time": tool_times.get((kind, event.get("toolCallId"))), "complete": False}
            rows.append(call)
            calls[event.get("toolCallId")] = call
        elif kind == "tool_execution_update":
            if event.get("toolCallId") in calls:
                calls[event["toolCallId"]]["partial_result"] = event.get("partialResult", event.get("result"))
        elif kind == "tool_execution_end":
            call_id = event.get("toolCallId")
            call = calls.get(call_id)
            if call is None:
                call = {"kind": "tool", "tool": event.get("toolName"), "call_id": call_id,
                        "event_line": line, "arguments": None, "missing_start": True}
                rows.append(call)
                calls[call_id] = call
            call.pop("partial_result", None)
            call.update(result=event.get("result"), is_error=bool(event.get("isError")), complete=True,
                        event_end_line=line, ended_at=tool_times.get((kind, call_id)))
        elif "compaction" in kind and (kind.endswith("_start") or kind.endswith("_end")):
            compactions.append({"event_line": line, **event})
            rows.append({"kind": "context_compaction", "event": kind, "event_line": line,
                         "reason": event.get("reason"), "aborted": event.get("aborted"),
                         "error": event.get("errorMessage"), "detail": event})
        elif kind in {"extension_ui_request", "extension_error"}:
            rows.append({"kind": "interface_event", "event_line": line, "detail": event,
                         "recorded_resolution": ui_resolutions.get(event.get("id"))})
    flush_pending(events[-1][0] if events else 0)
    return rows, compactions, ignored_updates


def request_audit(source, sources, turn, turn_summary, timeline):
    summaries = {}
    for item in (turn_summary or {}).get("requests", []):
        summaries[str(item.get("id"))] = item
    for path in sorted((source / "requests").glob("*/summary.json")):
        item = sources.json(path)
        if isinstance(item, dict) and item.get("turn") == turn:
            summaries[str(item.get("id", path.parent.name))] = item
    for _, item in timeline:
        if item.get("event") == "request_start" and item.get("turn") == turn:
            summaries.setdefault(str(item["id"]), {"id": item["id"], "incomplete": True,
                                                  "startedAt": item.get("time")})
    records = []
    for item in summaries.values():
        records.append({key: item.get(key) for key in (
            "id", "turn", "startedAt", "endedAt", "durationMs", "firstMs", "maxTokens", "messageCount",
            "httpStatus", "finishReason", "usage", "aborted", "error", "providerError", "incomplete") if key in item})
    records.sort(key=lambda item: int(item.get("id", 0)))
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
              "requests": len(records), "requests_with_usage": 0, "duration_ms_sum": 0}
    for record in records:
        if record.get("usage"):
            totals["requests_with_usage"] += 1
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                totals[key] += record["usage"].get(key, 0) or 0
        totals["duration_ms_sum"] += record.get("durationMs", 0) or 0
    return {"totals": totals, "requests": records,
            "accounting": "Provider request summaries only, including any compaction requests. Assistant/compaction usage is NOT added again. Missing usage stays unknown, not evidence of zero consumption."}


def build_session(root, source_name, alias, out, sources, limit):
    source, destination = root / source_name, out / "review" / alias
    destination.mkdir(parents=True, exist_ok=True)
    blind = Blind(root, source_name, alias)
    timeline = sources.jsonl(source / "timeline.jsonl", optional=True)
    status = sources.json(source / "status.json", optional=True) or {}
    manifest = sources.json(source / "manifest.json", optional=True) or {}
    audits, review_turns = [], []
    markdown = [f"# {alias} — researcher interaction record", "",
                "This is a source-backed transcript, not a score or a methodological verdict. Configuration labels and run-root paths are masked; substantive prompts, replies, tool names, arguments, errors and results are retained. Linked evidence contains complete sanitized tool records. Event-line order is authoritative; timestamps are shown only when recorded.", "",
                "Streaming updates are merged, not counted as repeated actions. A partial collection is explicitly marked; absence of a recorded result is not success. Original-source hashes and unblinding information are held separately in the private audit.", ""]
    for turn_dir in sorted((source / "turns").glob("*")):
        if not turn_dir.is_dir() or not turn_dir.name.isdigit():
            continue
        number = int(turn_dir.name)
        turn_label = f"turn-{number:03d}"
        turn_out = destination / turn_label
        turn_out.mkdir(parents=True, exist_ok=True)
        summary = sources.json(turn_dir / "summary.json", optional=True)
        prompt = sources.read(turn_dir / "prompt.txt")
        events = sources.jsonl(turn_dir / "events.jsonl")
        turn_timeline = [(line, row) for line, row in timeline if row.get("turn") == number]
        entries, compactions, delta_count = compact_events(events, turn_timeline)
        final = sources.read(turn_dir / "final_answer.txt", optional=True)
        if prompt is None:
            prompt = next((blocks_text(row.get("message", {}).get("content")) for _, row in events
                           if row.get("type") == "message_end" and row.get("message", {}).get("role") == "user"), "[Prompt not available in collected files]")
        complete = summary is not None and final is not None
        before_path, after_path = turn_dir / "state_before.json", turn_dir / "state_after.json"
        before = sources.json(before_path, optional=True)
        after = sources.json(after_path, optional=True)
        after_observed = after_path.exists()
        state_label = "state_after" if after_observed else "state_latest_observed"
        if not after_observed and number == int(status.get("turn", -1)):
            after = sources.json(source / "research/research_state.json", optional=True)
        diff = state_changes(before, after) if after_observed or after is not None else []
        write_json(turn_out / "state_before.json", blind.value(before))
        write_json(turn_out / f"{state_label}.json", blind.value(after))
        write_json(turn_out / "state_diff.json", blind.value({"after_kind": state_label, "changes": diff}))
        prompt_clean = blind.text(prompt)
        (turn_out / "prompt.txt").write_text(prompt_clean, encoding="utf-8")
        markdown.extend([f"## Turn {number}", "", f"Collection: {'closed turn' if complete else 'PARTIAL / closing records unavailable'}. Recorded outcome: {blind.text((summary or {}).get('outcome', 'unknown'))}.", "",
                         "### Human prompt (complete)", "", prompt_clean, "", "### Agent and tool timeline", ""])
        public_entries = [{"kind": "human", "text": prompt_clean, "evidence": f"{turn_label}/prompt.txt"}]
        tool_count, tool_error_count, evidence_map = 0, 0, []
        for sequence, raw_entry in enumerate(entries, 1):
            entry = blind.value(raw_entry)
            filename = f"event-{sequence:04d}.json"
            write_json(turn_out / filename, entry)
            link = f"{turn_label}/{filename}"
            evidence_map.append({"review_evidence": f"{alias}/{link}", "source": str(turn_dir / "events.jsonl"),
                                 "line": raw_entry.get("event_line"), "end_line": raw_entry.get("event_end_line")})
            public_entries.append({**entry, "evidence": link})
            locator = f"event line {entry.get('event_line', '?')}"
            when = f" · {entry['time']}" if entry.get("time") else ""
            if entry["kind"] == "tool":
                tool_count += 1
                tool_error_count += int(entry.get("is_error", False))
                state = "ERROR" if entry.get("is_error") else ("completed" if entry.get("complete") else "PENDING / no recorded end")
                result = entry.get("result", entry.get("partial_result"))
                preview = blocks_text(result.get("content")) if isinstance(result, dict) else ""
                if not preview:
                    preview = dumps(result)
                markdown.extend([f"#### {sequence}. Tool `{entry.get('tool')}` — {state}{when}", "",
                                 f"[{locator}; complete arguments and result]({link})", "", "Arguments:", "",
                                 "```json", short(dumps(entry.get("arguments")), limit), "```", "",
                                 "Result / error:", "", "```text", short(preview, limit), "```", ""])
            elif entry["kind"] in {"assistant", "assistant_partial"}:
                label = "Assistant (partial stream; not a final reply)" if entry["kind"] == "assistant_partial" else "Assistant message"
                markdown.extend([f"#### {sequence}. {label}{when}", "", f"[{locator}]({link})", "", entry.get("text", ""), ""])
                if entry.get("error"):
                    markdown.extend(["Recorded assistant error: " + entry["error"], ""])
            elif entry["kind"] == "context_compaction":
                markdown.extend([f"#### {sequence}. Context compaction event", "",
                                 f"{entry['event']}; reason={entry.get('reason')}; aborted={entry.get('aborted')}. [Complete recorded detail]({link}).", ""])
            else:
                markdown.extend([f"#### {sequence}. Interface event", "", f"[Complete event evidence]({link})", "", short(dumps(entry), limit), ""])
        if final is not None:
            final_clean = blind.text(final)
            (turn_out / "final_answer.txt").write_text(final_clean, encoding="utf-8")
            markdown.extend(["### Recorded final reply (complete)", "", final_clean if final_clean else "[The recorded final-answer file is empty.]", ""])
            public_entries.append({"kind": "recorded_final", "text": final_clean, "evidence": f"{turn_label}/final_answer.txt",
                                   "duplicate_of_last_assistant_text": bool(entries and any(e.get("kind") == "assistant" and blind.text(e.get("text", "")) == final_clean for e in entries))})
        else:
            markdown.extend(["### Recorded final reply", "", "Not available in this collection. Partial text above must not be treated as a final reply.", ""])
        overview = blind.value({"before": state_overview(before), state_label: state_overview(after), "changed_paths": [change["path"] for change in diff]})
        write_json(turn_out / "state_overview.json", overview)
        markdown.extend(["### State evidence", "", f"[Before]({turn_label}/state_before.json) · [{state_label}]({turn_label}/{state_label}.json) · [Main state summary]({turn_label}/state_overview.json) · [Complete structural changes]({turn_label}/state_diff.json)", "",
                         "```json", short(dumps({k: v for k, v in overview.items() if k != "changed_paths"}), limit), "```", ""])
        starts = [e for e in compactions if e["type"].endswith("_start")]
        ends = [e for e in compactions if e["type"].endswith("_end")]
        audit = {"turn": number, "collection_complete": complete, "outcome": (summary or {}).get("outcome"),
                 "started_at": (summary or {}).get("startedAt"), "ended_at": (summary or {}).get("endedAt"),
                 "duration_ms": (summary or {}).get("durationMs"), "failure": (summary or {}).get("failure"),
                 "tool_calls_started_or_observed": tool_count, "recorded_tool_errors": tool_error_count,
                 "stream_updates_merged_or_omitted": delta_count, "source_event_lines_parsed": len(events),
                 "compaction": {"start_events": len(starts), "end_events": len(ends),
                                "completed_end_events": sum(not e.get("aborted") and not e.get("errorMessage") for e in ends),
                                "aborted_or_error_end_events": sum(bool(e.get("aborted") or e.get("errorMessage")) for e in ends),
                                "events": blind.value(compactions)},
                 "request_accounting": blind.value(request_audit(source, sources, number, summary, timeline)),
                 "evidence_locators": evidence_map, "state_before_source": str(before_path),
                 "state_after_source": str(after_path) if after_observed else str(source / "research/research_state.json"),
                 "state_after_kind": state_label, "state_changed_path_count": len(diff)}
        audits.append(audit)
        review_turns.append({"turn": number, "collection_complete": complete, "entries": public_entries,
                             "state_overview": f"{turn_label}/state_overview.json"})
    artifact_rows = []
    for path in sorted((source / "research").rglob("run_manifest.json")):
        value = sources.json(path)
        if not isinstance(value, dict) or value.get("action") != "fit":
            continue
        artifact_id = f"fit-{len(artifact_rows) + 1:03d}"
        artifact_out = destination / "artifacts" / artifact_id
        write_json(artifact_out / "run_manifest.json", blind.value(value))
        records = []
        for name in ("model_summary.csv", "coefficient_summary.csv", "spatial_summary.csv"):
            table = path.parent / name
            if table.exists():
                content = sources.read(table)
                if content is not None:
                    (artifact_out / name).write_text(blind.text(content), encoding="utf-8")
                    records.append({"file": name, "sha256": sources.files[str(table.relative_to(root))]["sha256"]})
        artifact_rows.append({"artifact": artifact_id, "status": value.get("status"),
                              "manifest": f"artifacts/{artifact_id}/run_manifest.json", "tables": records,
                              "source_locator_id": f"{alias}/{artifact_id}"})
        audits.append({"artifact_locator_id": f"{alias}/{artifact_id}", "source_directory": str(path.parent)})
    if artifact_rows:
        write_json(destination / "artifact_index.json", artifact_rows)
        markdown.extend(["## Newly computed fit artifacts", "", "[Fit manifest and coefficient/model summaries](artifact_index.json). These are discovered only under this session's research directory, not a saved reference/gold directory. Presence is evidence of a file, not endorsement of its conclusions.", ""])
    (destination / "transcript.md").write_text("\n".join(markdown), encoding="utf-8")
    write_json(destination / "timeline.json", {"session": alias, "turns": review_turns})
    return {"anonymous_session": alias, "source_session": source_name,
            "source_condition": manifest.get("condition"), "source_context_mode": manifest.get("contextMode"),
            "status_at_collection": status, "turns_and_artifacts": audits}, len(review_turns)


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=project / "evaluation/long27_20260831")
    parser.add_argument("--out", type=Path, default=project / "evaluation/long27_20260831_review")
    parser.add_argument("--seed", type=int, default=20260831, help="Stable anonymous session order; key is private audit only")
    parser.add_argument("--result-chars", type=int, default=1600, help="Markdown tool-result/argument preview cap; linked evidence is complete")
    args = parser.parse_args()
    root, out = args.input.resolve(), args.out.resolve()
    if out == root or any(out == root / name or (root / name) in out.parents for name in ("A", "B")):
        parser.error("Output must not be the source root or inside source sessions A/B")
    names = [name for name in ("A", "B") if (root / name).is_dir()]
    if not names:
        parser.error("No downloaded A/B source directories found")
    random.Random(args.seed).shuffle(names)
    sources = Sources(root)
    audits, indexes = [], []
    for index, name in enumerate(names, 1):
        alias = f"Session-{index:02d}"
        audit, turn_count = build_session(root, name, alias, out, sources, max(args.result_chars, 200))
        audits.append(audit)
        indexes.append({"session": alias, "turn_count": turn_count, "transcript": f"{alias}/transcript.md", "timeline_json": f"{alias}/timeline.json"})
    write_json(out / "audit.json", {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
                                    "warning": "PRIVATE: unblinding key and original source locations. Do not give this file to blinded judges.",
                                    "source_root": str(root), "script_sha256": digest(Path(__file__).read_bytes()),
                                    "anonymous_order_seed": args.seed, "sessions": audits,
                                    "source_files": sources.files, "collection_issues": sources.issues,
                                    "source_scope": "turn prompts/finals/events/states, timeline/status/manifest, request summaries, and newly computed research fit summaries only; no runtime auth, request bodies, legacy gold or raw device inputs"})
    write_json(out / "review/index.json", indexes)
    readme = ["# Blinded long-workflow researcher materials", "",
              "Read the complete interaction timeline and linked tool evidence, not only final answers. These materials contain no scores, reference answers or winner labels. Configuration identifiers are masked; tool behavior and errors are not hidden. Source collection can be partial and is labeled per turn. Files in this review directory are shareable; the sibling audit.json is private and contains the unblinding key, token/time accounting and original-source mappings.", "",
              "Paths: [SESSION_ROOT] means that session's original working root; [TOOL_ROOT] means the shared analysis-tool/data directory. Public evidence links point to sanitized local copies. Any shortened Markdown tool output has a complete linked JSON record. Structural state differences are machine-generated, without interpreting whether a change was correct.", ""]
    readme.extend(f"- [{item['session']} — {item['turn_count']} collected turns]({item['transcript']})" for item in indexes)
    (out / "review/README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(json.dumps({"status": "created", "review": str(out / "review"), "private_audit": str(out / "audit.json"),
                      "sessions": len(indexes), "turns": sum(item["turn_count"] for item in indexes),
                      "collection_issues": len(sources.issues), "scored": False}, ensure_ascii=False))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
