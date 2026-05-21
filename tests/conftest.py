"""Shared pytest fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

# Make ``scripts/`` importable as top-level modules from tests.
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
