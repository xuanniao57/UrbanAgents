"""GIS layer-stack export tool facade."""

from __future__ import annotations

from typing import Any, Dict



def build_gis_artifact_bundle(arguments: Dict[str, Any]) -> Dict[str, Any]:
    from ..geo_tools import build_gis_artifact_bundle as _build

    return _build(arguments)
