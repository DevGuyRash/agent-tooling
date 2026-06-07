#!/usr/bin/env python3
"""Hook helper to import Goal Foundry skill script common.py."""
from __future__ import annotations
import os
import sys
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[2])
SCRIPTS = PLUGIN_ROOT / "skills" / "authoring-goals" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
