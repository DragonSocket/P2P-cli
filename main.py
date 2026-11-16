#!/usr/bin/env python3
"""Compatibility entry point for the new CLI (old flags are in legacy/main.py)."""
from p2pvpn.cli import main
raise SystemExit(main())
