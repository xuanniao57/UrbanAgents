#!/usr/bin/env python
"""Seed Case 2 literature-derived research memory for Urban-Hermes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def _find_paper4_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "hermes_urban_agent" / "urban_hermes" / "launcher.py").exists():
            return candidate
    raise RuntimeError("Could not locate paper4_urban_svgagent root from script path.")


PAPER4_ROOT = _find_paper4_root(Path(__file__).resolve())
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
for import_path in (PAPER4_ROOT / "hermes_urban_agent", PAPER4_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False, default=str) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _normalize_seed_record(record: dict[str, Any], *, source_kind: str) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("timestamp", "seed")
    normalized.setdefault("memory_type", normalized.get("content_layer") or "research_design")
    normalized.setdefault("memory_scope", "reflective")
    normalized.setdefault("memory_chain", "research_chain")
    normalized.setdefault("linked_memory_chains", [normalized["memory_chain"]])
    normalized.setdefault("source_kind", source_kind)
    normalized.setdefault("promotion_state", "seed")
    if not normalized.get("record_id"):
        raise ValueError(f"Seed memory record is missing record_id: {normalized}")
    return normalized


def _records_from_extracted_memory(extracted_dir: Path) -> list[dict[str, Any]]:
    records = []
    if not extracted_dir.exists():
        return records
    for memory_path in sorted(extracted_dir.glob("*.json")):
        try:
            payload = _load_json(memory_path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        paper_id = str(payload.get("paper_id") or memory_path.stem)
        title = str(payload.get("title") or paper_id)
        blocked_claims = payload.get("blocked_claims") or []
        reuse_rules = payload.get("case2_reuse_rules") or []
        workflow_steps = payload.get("workflow_steps") or []
        records.append(
            _normalize_seed_record(
                {
                    "record_id": f"case2_extracted_{paper_id}",
                    "memory_type": "research_design",
                    "memory_scope": "reflective",
                    "memory_chain": "research_chain",
                    "content_layer": "research_design",
                    "domain": "case2_extracted_paper_memory",
                    "summary": f"Paper memory for {title}: reuse its research flow only as a Case 2 design cue, with explicit blocked claims and data requirements.",
                    "triggers": [paper_id, title, "Case2", "literature memory", "文献记忆"],
                    "method_hint": "Use this extracted paper memory to compare problem framing, data evidence, method gates, workflow steps, and claim limits before choosing Case 2 methods.",
                    "caveats": blocked_claims,
                    "source": {"file": str(memory_path), "paper_id": paper_id, "title": title},
                    "payload": {
                        "research_flow": payload.get("research_flow") or [],
                        "problem_data_method_triples": payload.get("problem_data_method_triples") or [],
                        "workflow_steps": workflow_steps,
                        "case2_reuse_rules": reuse_rules,
                        "blocked_claims": blocked_claims,
                    },
                },
                source_kind="case2_extracted_memory",
            )
        )
    return records


def _case2_source_kind(record: dict[str, Any]) -> bool:
    return str(record.get("source_kind") or "").startswith("case2_") or str(record.get("record_id") or "").startswith("case2_lit_") or str(record.get("record_id") or "").startswith("case2_extracted_")


def _memory_root_from_args(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    if os.getenv("URBAN_HERMES_MEMORY_ROOT"):
        return Path(os.environ["URBAN_HERMES_MEMORY_ROOT"]).expanduser().resolve()
    return PACKAGE_ROOT / "hermes_memory"


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Case 2 literature memory cards into Urban-Hermes research memory.")
    parser.add_argument("--cards", default=str(PACKAGE_ROOT / "literature_memory" / "case2_research_memory_cards.json"))
    parser.add_argument("--extracted-dir", default=str(PACKAGE_ROOT / "literature_memory" / "extracted_memory"))
    parser.add_argument("--memory-root", default=None)
    parser.add_argument("--replace-case2", action="store_true", help="Remove previous Case 2 seeded records before importing.")
    parser.add_argument("--summary-output", default="D:/UrbanAgents_Case2_Output/preflight/case2_research_memory_seed.json")
    parser.add_argument("--probe-query", default="街道活力 街景感知 建成环境 非线性 空间异质性")
    args = parser.parse_args()

    cards_path = Path(args.cards).resolve()
    memory_root = _memory_root_from_args(args.memory_root)
    memory_path = memory_root / "research_memory" / "research_lessons.jsonl"
    seed_cards = [_normalize_seed_record(item, source_kind="case2_literature_seed") for item in _load_json(cards_path)]
    extracted_cards = _records_from_extracted_memory(Path(args.extracted_dir).resolve())
    import_records = seed_cards + extracted_cards

    existing_records = _read_jsonl(memory_path)
    if args.replace_case2:
        existing_records = [record for record in existing_records if not _case2_source_kind(record)]

    existing_ids = {str(record.get("record_id")) for record in existing_records}
    inserted = []
    skipped = []
    for record in import_records:
        record_id = str(record.get("record_id"))
        if record_id in existing_ids:
            skipped.append(record_id)
            continue
        existing_records.append(record)
        existing_ids.add(record_id)
        inserted.append(record_id)
    _write_jsonl(memory_path, existing_records)

    os.environ["URBAN_HERMES_MEMORY_ROOT"] = str(memory_root)
    from urban_hermes.memory_provider import UrbanMemoryProvider

    provider = UrbanMemoryProvider(memory_root)
    provider.initialize("case2_research_memory_seed")
    hits = provider.research.search(args.probe_query, limit=5, memory_scopes={"reflective"}, memory_chains={"research_chain"})

    summary = {
        "success": True,
        "cards_path": str(cards_path),
        "memory_root": str(memory_root),
        "memory_path": str(memory_path),
        "inserted_count": len(inserted),
        "skipped_count": len(skipped),
        "inserted_record_ids": inserted,
        "skipped_record_ids": skipped,
        "probe_query": args.probe_query,
        "probe_hits": [
            {"record_id": hit.get("record_id"), "summary": hit.get("summary"), "content_layer": hit.get("content_layer")}
            for hit in hits
        ],
    }
    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()