#!/usr/bin/env python3
"""Compatibility wrapper for older chip-netlist parser entrypoint."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from parse_project import *  # noqa: F401,F403
from parse_project import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
