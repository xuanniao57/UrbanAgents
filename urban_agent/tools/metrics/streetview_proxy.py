"""Street-view proxy metric tool facade."""

from __future__ import annotations

from typing import Any, Dict



def compute_streetview_visual_consistency(arguments: Dict[str, Any]) -> Dict[str, Any]:
    from ..geo_tools import compute_streetview_visual_consistency as _compute

    return _compute(arguments)
