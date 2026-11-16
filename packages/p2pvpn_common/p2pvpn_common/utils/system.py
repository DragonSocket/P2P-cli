"""System-level utilities: privilege checks, platform detection."""
from __future__ import annotations

import os
import sys


def is_admin() -> bool:
    """root on Linux, Administrator on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return os.geteuid() == 0


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_windows() -> bool:
    return sys.platform == "win32"
