"""Shared paths for UrbanAgent installation and runtime data."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
LEGACY_URBAN_HOME = Path.home() / ".urban-agent"


def _default_urban_home() -> Path:
    return Path.cwd() / ".urban-agent"


def get_urban_home() -> Path:
    """Return the user data directory for config, runs, sessions, and logs."""
    override = os.getenv("URBAN_AGENT_HOME") or os.getenv("URBAN_AGENT_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _default_urban_home().expanduser().resolve()


def get_install_root() -> Path:
    """Return the preferred code checkout/install directory."""
    override = os.getenv("URBAN_AGENT_INSTALL_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return PACKAGE_ROOT


def get_config_path() -> Path:
    return get_urban_home() / "config.yaml"


def get_env_path() -> Path:
    return get_urban_home() / ".env"


def get_runs_dir(configured: Optional[str] = None) -> Path:
    override = os.getenv("URBAN_AGENT_RUNS_DIR") or configured
    if override:
        return Path(override).expanduser().resolve()
    return get_urban_home() / "runs"


def get_sessions_dir() -> Path:
    return get_urban_home() / "sessions"


def get_logs_dir() -> Path:
    return get_urban_home() / "logs"


def get_cache_dir() -> Path:
    return get_urban_home() / "cache"


def display_urban_home() -> str:
    home = Path.home().resolve()
    urban_home = get_urban_home()
    try:
        rel = urban_home.relative_to(home)
    except ValueError:
        return str(urban_home)
    return str(Path("~") / rel)


def ensure_urban_home() -> Path:
    urban_home = get_urban_home()
    for directory in (
        urban_home,
        get_runs_dir(),
        get_sessions_dir(),
        get_logs_dir(),
        get_cache_dir(),
        urban_home / "data",
        urban_home / "tools",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return urban_home
