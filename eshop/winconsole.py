"""Windows console setup.

The legacy console window (conhost, what you get by double-clicking an .exe)
does not fall back to other fonts, so with Consolas or Lucida Console every
Japanese character is drawn as a box or '?'. On start-up we therefore switch
the window to UTF-8 and to a font that ships with every Windows edition and
covers Japanese ("MS Gothic"). Windows Terminal already does font fallback,
so it is left alone.

Override with the ESHOP_FONT environment variable: a font face name, or
"none" to leave the console untouched.
"""

from __future__ import annotations

import os
import sys

DEFAULT_FONT = "MS Gothic"


def setup() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.windll.kernel32
        k32.SetConsoleOutputCP(65001)
        k32.SetConsoleCP(65001)

        font = os.environ.get("ESHOP_FONT", DEFAULT_FONT).strip()
        if font.lower() == "none" or os.environ.get("WT_SESSION"):
            return
        if not sys.stdout or not sys.stdout.isatty():
            return

        class COORD(ctypes.Structure):
            _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

        class CONSOLE_FONT_INFOEX(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.ULONG),
                ("nFont", wintypes.DWORD),
                ("dwFontSize", COORD),
                ("FontFamily", wintypes.UINT),
                ("FontWeight", wintypes.UINT),
                ("FaceName", wintypes.WCHAR * 32),
            ]

        handle = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        info = CONSOLE_FONT_INFOEX()
        info.cbSize = ctypes.sizeof(CONSOLE_FONT_INFOEX)
        if not k32.GetCurrentConsoleFontEx(handle, False, ctypes.byref(info)):
            return
        if info.FaceName.lower() == font.lower():
            return
        info.FaceName = font
        info.FontFamily = 0x30 | 0x01   # FF_MODERN | FIXED_PITCH
        info.FontWeight = 400
        if info.dwFontSize.Y < 14:       # MS Gothic is thin; keep it readable
            info.dwFontSize.X = 0
            info.dwFontSize.Y = 16
        k32.SetCurrentConsoleFontEx(handle, False, ctypes.byref(info))
    except Exception:
        # purely cosmetic; never let console tweaking break the program
        pass
