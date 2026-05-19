#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare a one-paper MinerU input file from the Case 2 literature manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = ("paper_id", "title", "pdfPath")


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


def find_paper(manifest: dict[str, Any], paper_id: str) -> dict[str, Any]:
    for paper in manifest.get("papers", []):
        if paper.get("paper_id") == paper_id:
            return paper
    available_ids = [paper.get("paper_id", "") for paper in manifest.get("papers", [])]
    raise ValueError(f"Unknown paper_id: {paper_id}. Available ids: {', '.join(available_ids)}")


def validate_paper(paper: dict[str, Any]) -> None:
    missing_fields = [field_name for field_name in REQUIRED_FIELDS if not paper.get(field_name)]
    if missing_fields:
        raise ValueError(f"Paper entry is missing required fields: {', '.join(missing_fields)}")

    pdf_path = Path(paper["pdfPath"])
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF does not exist: {pdf_path}")


def build_mineru_input(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "papers": [
            {
                "itemKey": paper["paper_id"],
                "title": paper["title"],
                "pdfPath": paper["pdfPath"],
                "role": paper.get("role", ""),
                "memory_focus": paper.get("memory_focus", []),
            }
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a single-paper MinerU input JSON.")
    parser.add_argument("--manifest", required=True, help="Path to selected_papers.json")
    parser.add_argument("--paper-id", required=True, help="paper_id from selected_papers.json")
    parser.add_argument("--output-dir", required=True, help="Directory for single-paper JSON files")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(manifest_path)
    paper = find_paper(manifest, args.paper_id)
    validate_paper(paper)

    mineru_input = build_mineru_input(paper)
    output_path = output_dir / f"{paper['paper_id']}.json"
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(mineru_input, output_file, ensure_ascii=False, indent=2)

    print(f"Wrote one-paper MinerU input: {output_path}")
    print("Next command:")
    print(
        "python C:/Users/18029/.claude/skills/zotero-pdf-analyzer/scripts/mineru_api_v4.py "
        f"--input {output_path} --output ../literature_memory/mineru_output --batch-size 1 --model-version vlm"
    )


if __name__ == "__main__":
    main()
