"""Tiny table renderer that keeps CJK (double width) text aligned."""

from __future__ import annotations

import csv
import json
import os
import shutil
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


def wrap(s: str, max_width: int) -> list[str]:
    """Word-wrap `s` to `max_width` display cells (CJK aware)."""
    if width(s) <= max_width:
        return [s]
    lines: list[str] = []
    cur = ""
    for word in s.split(" "):
        while width(word) > max_width:          # a single over-long token
            if cur:
                lines.append(cur)
                cur = ""
            head = ""
            for ch in word:
                if width(head + ch) > max_width:
                    break
                head += ch
            lines.append(head)
            word = word[len(head):]
        cand = word if not cur else cur + " " + word
        if width(cand) <= max_width:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def pad(s: str, w: int, right: bool = False) -> str:
    fill = " " * max(0, w - width(s))
    return fill + s if right else s + fill


def terminal_width(file) -> int | None:
    """Columns available when writing to an interactive console, else None."""
    try:
        if file is not None and file is not sys.stdout:
            return None
        if not sys.stdout.isatty():
            return None
    except (AttributeError, ValueError):
        return None
    env = os.environ.get("ESHOP_WIDTH")
    if env and env.isdigit():
        return int(env)
    return shutil.get_terminal_size((120, 40)).columns


def render(headers: Sequence[str], rows: Iterable[Sequence], *, numeric: Sequence[int] = (),
           max_col: int = 60, flex: Sequence[int] | None = None,
           optional: Sequence[int] = (), file=None) -> None:
    """Print an aligned table that fits the console.

    To make it fit, in order: the `flex` columns (default: the widest text
    column) are narrowed to 30 cells, then columns that are empty in every
    row are dropped, then the `optional` columns are dropped one by one,
    and finally the flex columns are narrowed further (never below 16).
    Text that no longer fits a flex column wraps onto continuation lines;
    other columns are truncated with an ellipsis.
    """
    file = file or sys.stdout
    headers = list(headers)
    rows = [["" if c is None else str(c) for c in r] for r in rows]
    n = len(headers)
    numeric = set(numeric)
    if flex is None:
        guess = max(range(n), key=lambda k: (max([width(h) for h in [headers[k]]] +
                                             [width(r[k]) for r in rows]) if k not in numeric else -1))
        flex = [guess]
    flex = set(flex)
    keep = list(range(n))
    widths = {i: max([width(headers[i])] + [width(r[i]) for r in rows]) for i in keep}
    widths = {i: min(w, max_col) for i, w in widths.items()}

    term = terminal_width(file)

    def total():
        return sum(widths[i] for i in keep) + 2 * (len(keep) - 1)

    def narrow(floor):
        while term and total() > term - 1:
            cands = [i for i in keep if i in flex and widths[i] > floor]
            if not cands:
                return
            i = max(cands, key=lambda k: widths[k])
            widths[i] -= 1

    if term:
        narrow(30)
        if total() > term - 1:
            for i in list(keep):
                if i not in flex and all(r[i] == "" for r in rows) and len(keep) > 1:
                    keep.remove(i)
        for i in optional:
            if total() <= term - 1:
                break
            if i in keep and len(keep) > 1:
                keep.remove(i)
        narrow(16)

    def cell(i, text):
        return pad(truncate(text, widths[i]), widths[i], i in numeric)

    print("  ".join(cell(i, headers[i]) for i in keep), file=file)
    print("  ".join("-" * widths[i] for i in keep), file=file)
    for r in rows:
        # flex columns wrap; every other column is a single (truncated) line
        parts = {i: (wrap(r[i], widths[i]) if i in flex else [truncate(r[i], widths[i])]) for i in keep}
        height = max(len(v) for v in parts.values())
        for ln in range(height):
            print("  ".join(pad(parts[i][ln] if ln < len(parts[i]) else "", widths[i], i in numeric)
                            for i in keep), file=file)


def write_csv(headers: Sequence[str], rows: Iterable[Sequence], file=None) -> None:
    w = csv.writer(file or sys.stdout)
    w.writerow(headers)
    for r in rows:
        w.writerow(["" if c is None else c for c in r])


def write_json(headers: Sequence[str], rows: Iterable[Sequence], file=None) -> None:
    json.dump([dict(zip(headers, r)) for r in rows], file or sys.stdout,
              ensure_ascii=False, indent=2)
    print(file=file or sys.stdout)
