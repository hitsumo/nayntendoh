"""Tiny table renderer that keeps CJK (double width) text aligned."""

from __future__ import annotations

import csv
import json
import sys
import unicodedata
from typing import Iterable, Sequence


def width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def truncate(s: str, max_width: int) -> str:
    if width(s) <= max_width:
        return s
    out = ""
    for ch in s:
        if width(out + ch) > max_width - 1:
            break
        out += ch
    return out + "…"


def pad(s: str, w: int, right: bool = False) -> str:
    fill = " " * max(0, w - width(s))
    return fill + s if right else s + fill


def render(headers: Sequence[str], rows: Iterable[Sequence], *, numeric: Sequence[int] = (),
           max_col: int = 60, file=None) -> None:
    file = file or sys.stdout
    rows = [[truncate("" if c is None else str(c), max_col) for c in r] for r in rows]
    widths = [width(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], width(c))
    line = "  ".join(pad(h, widths[i], i in numeric) for i, h in enumerate(headers))
    print(line, file=file)
    print("  ".join("-" * w for w in widths), file=file)
    for r in rows:
        print("  ".join(pad(c, widths[i], i in numeric) for i, c in enumerate(r)), file=file)


def write_csv(headers: Sequence[str], rows: Iterable[Sequence], file=None) -> None:
    w = csv.writer(file or sys.stdout)
    w.writerow(headers)
    for r in rows:
        w.writerow(["" if c is None else c for c in r])


def write_json(headers: Sequence[str], rows: Iterable[Sequence], file=None) -> None:
    json.dump([dict(zip(headers, r)) for r in rows], file or sys.stdout,
              ensure_ascii=False, indent=2)
    print(file=file or sys.stdout)
