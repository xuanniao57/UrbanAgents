"""Function-mix metric tool facade."""

from __future__ import annotations

from typing import Any, Dict



def compute_function_mix_entropy(arguments: Dict[str, Any]) -> Dict[str, Any]:
    from ..geo_tools import compute_function_mix_entropy as _compute

    return _compute(arguments)
