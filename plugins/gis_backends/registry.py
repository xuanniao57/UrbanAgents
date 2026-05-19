"""Small registry for GIS backend adapters."""

from __future__ import annotations

from typing import Any

from .protocol import BACKEND_ARCGIS_PRO, BACKEND_QGIS_DESKTOP, normalize_backend_id


def list_backends() -> list[str]:
    return [BACKEND_QGIS_DESKTOP, BACKEND_ARCGIS_PRO]


def get_backend(backend_id: object | None = None) -> Any:
    normalized = normalize_backend_id(backend_id)
    if normalized == BACKEND_QGIS_DESKTOP:
        from .qgis_desktop import backend

        return backend
    if normalized == BACKEND_ARCGIS_PRO:
        from .arcgis_pro import backend

        return backend
    raise ValueError(f"unsupported GIS backend: {normalized}; available={list_backends()}")