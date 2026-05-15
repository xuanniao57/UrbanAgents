"""Path bootstrap for the separate Hermes-Urban adapter."""

from __future__ import annotations

import os
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
PROJECT_ROOT = REPO_ROOT.parent if REPO_ROOT.name == "paper4_urban_svgagent" else REPO_ROOT
VENDORED_HERMES_ROOT = Path(__file__).resolve().parent / "_vendor" / "hermes_runtime"


def _default_hermes_root() -> Path:
    override = os.getenv("URBAN_HERMES_HERMES_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if VENDORED_HERMES_ROOT.exists():
        return VENDORED_HERMES_ROOT.resolve()
    return (PROJECT_ROOT / "hermes-agent").resolve()


HERMES_ROOT = _default_hermes_root()
_default_paper4_root = REPO_ROOT if (REPO_ROOT / "urban_agent").exists() else PROJECT_ROOT / "paper4_urban_svgagent"
PAPER4_ROOT = Path(os.getenv("URBAN_HERMES_URBAN_AGENT_ROOT", _default_paper4_root)).expanduser().resolve()


def _default_urban_home() -> Path:
    return Path(
        os.getenv("URBAN_AGENTS_HOME")
        or os.getenv("URBAN_AGENT_HOME")
        or Path.cwd() / ".urban-agent"
    ).expanduser()


def _default_memory_root() -> Path:
    source_runtime = PACKAGE_ROOT / "runtime_memory"
    if source_runtime.exists() or (PACKAGE_ROOT / ".gitignore").exists():
        return source_runtime
    urban_home = _default_urban_home()
    return urban_home / "urban_hermes_memory"


DEFAULT_MEMORY_ROOT = _default_memory_root()
DEFAULT_HERMES_HOME = _default_urban_home() / "urban_hermes"


def ensure_paths() -> None:
    """Make Hermes and current UrbanAgent sources importable."""
    for path in reversed((HERMES_ROOT, PAPER4_ROOT, PACKAGE_ROOT)):
        if path.exists() and str(path) not in sys.path:
            sys.path.insert(0, str(path))
    os.environ.setdefault("HERMES_HOME", str(DEFAULT_HERMES_HOME))
    os.environ.setdefault("URBAN_HERMES_MEMORY_ROOT", str(DEFAULT_MEMORY_ROOT))
    os.environ.setdefault("URBAN_AGENT_MEMORY_ROOT", str(DEFAULT_MEMORY_ROOT / "urban_agent"))


ensure_paths()
