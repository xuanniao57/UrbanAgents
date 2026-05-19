"""Shared protocol constants for GIS backend adapters."""

from __future__ import annotations


BACKEND_QGIS_DESKTOP = "qgis_desktop"
BACKEND_ARCGIS_PRO = "arcgis_pro"
BACKEND_AUTO = "auto"

MODE_PROBE = "probe"
MODE_PACKAGE = "package"
MODE_VALIDATE = "validate"
MODE_PACKAGE_AND_VALIDATE = "package_and_validate"

SUPPORTED_MODES = {MODE_PROBE, MODE_PACKAGE, MODE_VALIDATE, MODE_PACKAGE_AND_VALIDATE}


def normalize_backend_id(value: object | None) -> str:
    backend_id = str(value or BACKEND_AUTO).strip().lower()
    if backend_id in {"", BACKEND_AUTO, "qgis", "qgis-desktop"}:
        return BACKEND_QGIS_DESKTOP
    if backend_id in {"arcgis", "arcgis-pro", "arcpy"}:
        return BACKEND_ARCGIS_PRO
    return backend_id


def normalize_mode(value: object | None) -> str:
    mode = str(value or MODE_PACKAGE_AND_VALIDATE).strip().lower()
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"unsupported GIS backend mode: {mode}")
    return mode