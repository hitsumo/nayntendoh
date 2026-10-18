"""Price lookups against Nintendo's public price API.

GET https://api.ec.nintendo.com/v1/price?country=DE&lang=en&ids=a,b,c
accepts at most 50 NSUIDs per call and only knows the NSUIDs that belong to
the catalog of the requested country (see regions.py).
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable

import requests

from .http import get_json

PRICE_URL = "https://api.ec.nintendo.com/v1/price"
BATCH = 50


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_price(country: str, entry: dict) -> dict:
    reg = entry.get("regular_price") or {}
    disc = entry.get("discount_price") or {}
    return {
        "nsuid": str(entry["title_id"]),
        "country": country,
        "sales_status": entry.get("sales_status", "unknown"),
        "currency": reg.get("currency") or disc.get("currency") or "",
        "regular_price": _num(reg.get("raw_value")),
        "regular_price_text": reg.get("amount") or "",
        "discount_price": _num(disc.get("raw_value")),
        "discount_price_text": disc.get("amount") or "",
        "discount_start": disc.get("start_datetime") or "",
        "discount_end": disc.get("end_datetime") or "",
    }


def fetch_batch(country: str, nsuids: list[str]) -> list[dict]:
    if not nsuids:
        return []
    try:
        data = get_json(PRICE_URL, params={
            "country": country, "lang": "en", "limit": BATCH, "ids": ",".join(nsuids),
        })
    except requests.RequestException as exc:
        # one bad batch must not abort the whole country
        print(f"\nwarning: {country}: batch of {len(nsuids)} ids failed: {exc}", file=sys.stderr)
        return []
    return [parse_price(country, e) for e in data.get("prices", [])]


def fetch_prices(country: str, nsuids: Iterable[str], workers: int = 6,
                 progress: Callable[[int, int], None] | None = None) -> list[dict]:
    """Fetch prices for all NSUIDs of one country, batching 50 per request."""
    ids = list(dict.fromkeys(str(n) for n in nsuids if str(n).isdigit()))
    batches = [ids[i:i + BATCH] for i in range(0, len(ids), BATCH)]
    results: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_batch, country, b) for b in batches]
        for fut in as_completed(futures):
            results.extend(fut.result())
            done += 1
            if progress:
                progress(done, len(batches))
    return results
