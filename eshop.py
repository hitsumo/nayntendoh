#!/usr/bin/env python3
"""Convenience launcher: `python eshop.py …` is the same as `python -m eshop …`."""
from eshop.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
