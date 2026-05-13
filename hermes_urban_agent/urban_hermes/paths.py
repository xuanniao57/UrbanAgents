"""Path bootstrap for the separate Hermes-Urban adapter."""

from __future__ import annotations

import os
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
PROJECT_ROOT = REPO_ROOT.parent if REPO_ROOT.name == "paper4_urban_svgagent" else REPO_ROOT
HERMES_ROOT = Path(os.getenv("URBAN_HERMES_HERMES_ROOT", PROJECT_ROOT / "hermes-agent")).expanduser().resolve()
_default_paper4_root = REPO_ROOT if (REPO_ROOT / "urban_agent").exists() else PROJECT_ROOT / "paper4_urban_svgagent"
PAPER4_ROOT = Path(os.getenv("URBAN_HERMES_URBAN_AGENT_ROOT", _default_paper4_root)).expanduser().resolve()
DEFAULT_MEMORY_ROOT = PACKAGE_ROOT / "runtime_memory"


def ensure_paths() -> None:
    """Make Hermes and current UrbanAgent sources importable."""
    for path in (str(HERMES_ROOT), str(PAPER4_ROOT), str(PACKAGE_ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)
    os.environ.setdefault("URBAN_HERMES_MEMORY_ROOT", str(DEFAULT_MEMORY_ROOT))
    os.environ.setdefault("URBAN_AGENT_MEMORY_ROOT", str(DEFAULT_MEMORY_ROOT / "urban_agent"))


ensure_paths()
