"""Helpers for normalized backend validation reports."""

from __future__ import annotations

from typing import Any


def acceptance_from_report(report: dict[str, Any]) -> dict[str, Any]:
    blocking = list(report.get("blocking_errors") or [])
    if report.get("needs_correction") and not blocking:
        blocking.append("validation reported needs_correction=true")
    return {
        "accepted": not bool(blocking),
        "blocking_errors": blocking,
        "warnings": list(report.get("warnings") or []),
        "known_limits": list(report.get("known_limits") or []),
    }