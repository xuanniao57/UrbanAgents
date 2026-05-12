"""Built-form metric tool facade."""

from __future__ import annotations

from typing import Any, Dict


def compute_built_form_metrics(arguments: Dict[str, Any]) -> Dict[str, Any]:
    from ..geo_tools import compute_built_form_metrics as _compute

    return _compute(arguments)
