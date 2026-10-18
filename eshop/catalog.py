"""Catalog fetchers for the three Nintendo eShop regions.

Each fetcher yields plain dicts with the same keys:

    nsuid, region, title, publisher, release_date (YYYY-MM-DD or ''),
    product_code, platform, image_url, url
"""

from __future__ import annotations

import re
from typing import Callable, Iterator

from .http import get_json, post_json

Progress = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


# ---------------------------------------------------------------------------
# Europe  (search.nintendo-europe.com, Solr)
# ---------------------------------------------------------------------------

EU_SEARCH = "https://search.nintendo-europe.com/en/select"
EU_FIELDS = ("title,nsuid_txt,product_code_txt,date_from,image_url_sq_s,"
             "publisher,url,system_type,eshop_removed_b")


def fetch_eu(progress: Progress = _noop, page_size: int = 1000) -> Iterator[dict]:
    start = 0
    total = None
    while total is None or start < total:
        data = get_json(EU_SEARCH, params={
            "q": "*",
            "fq": "type:GAME AND system_type:nintendoswitch*",
            "fl": EU_FIELDS,
            "sort": "sorting_title asc",
            "rows": page_size,
            "start": start,
            "wt": "json",
        })
        resp = data["response"]
        total = resp["numFound"]
        docs = resp["docs"]
        if not docs:
            break
        for d in docs:
            nsuids = d.get("nsuid_txt") or []
            if not nsuids:
                continue
            systems = d.get("system_type") or []
            platform = "Nintendo Switch 2" if "nintendoswitch2" in systems else "Nintendo Switch"
            codes = [c for c in (d.get("product_code_txt") or []) if c]
            yield {
                "nsuid": str(nsuids[0]),
                "region": "eu",
                "title": d.get("title", "").strip(),
                "publisher": d.get("publisher") or "",
                "release_date": (d.get("date_from") or "")[:10],
                "product_code": codes[0] if codes else "",
                "platform": platform,
                "image_url": d.get("image_url_sq_s") or "",
                "url": ("https://www.nintendo.co.uk" + d["url"]) if d.get("url") else "",
            }
        start += len(docs)
        progress(f"EU: {min(start, total)}/{total}")


# ---------------------------------------------------------------------------
# Americas  (nintendo.com, public Algolia index)
# ---------------------------------------------------------------------------

ALGOLIA_APP = "U3B6GR4UA3"
ALGOLIA_KEY = "a29c6927638bfd8cee23993e51e721c9"   # public search-only key used by nintendo.com
ALGOLIA_INDEX = "store_game_en_us"
ALGOLIA_URL = f"https://{ALGOLIA_APP}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
ALGOLIA_HEADERS = {
    "x-algolia-application-id": ALGOLIA_APP,
    "x-algolia-api-key": ALGOLIA_KEY,
}
ALGOLIA_ATTRS = ["nsuid", "title", "softwarePublisher", "softwareDeveloper",
                 "releaseDate", "productImage", "url", "platform", "price"]
ALGOLIA_PAGE = 500          # distinct=false lets us go above the default 100
ALGOLIA_MAX = 1000          # Algolia refuses to paginate past 1000 hits


def _algolia(filters: str, page: int = 0, hits_per_page: int = ALGOLIA_PAGE,
             attrs=None, facets=None, max_values_per_facet: int | None = None) -> dict:
    payload = {
        "query": "",
        "filters": filters,
        "page": page,
        "hitsPerPage": hits_per_page,
        "distinct": False,
        "attributesToRetrieve": attrs if attrs is not None else ALGOLIA_ATTRS,
    }
    if facets:
        payload["facets"] = facets
    if max_values_per_facet:
        payload["maxValuesPerFacet"] = max_values_per_facet
    return post_json(ALGOLIA_URL, payload, headers=ALGOLIA_HEADERS)


def _algolia_count(filters: str) -> int:
    return _algolia(filters, hits_per_page=1, attrs=[])["nbHits"]


def _algolia_all(filters: str) -> Iterator[dict]:
    page = 0
    while True:
        data = _algolia(filters, page=page)
        for h in data["hits"]:
            yield h
        page += 1
        if page >= data["nbPages"]:
            break


def _publisher_buckets(filters: str) -> Iterator[str]:
    """Split a filter that still has > 1000 hits by publisher facet values."""
    data = _algolia(filters, hits_per_page=0, attrs=[], facets=["softwarePublisher"],
                    max_values_per_facet=1000)
    for publisher in (data.get("facets") or {}).get("softwarePublisher", {}):
        escaped = publisher.replace('\\', '\\\\').replace('"', '\\"')
        yield f'{filters} AND softwarePublisher:"{escaped}"'
    # titles without a publisher facet: the plain (capped) query catches them
    yield filters


def _price_buckets(base: str, lo: float, hi: float) -> Iterator[str]:
    """Split [lo, hi) on price.regPrice until each bucket has <= 1000 hits.

    Many titles share the exact same price point (e.g. 2000+ games at $4.99),
    so once an interval cannot be split any further the remaining bucket is
    split by publisher instead.
    """
    f = f"{base} AND price.regPrice >= {lo} AND price.regPrice < {hi}"
    n = _algolia_count(f)
    if n == 0:
        return
    if n <= ALGOLIA_MAX:
        yield f
        return
    mid = round((lo + hi) / 2, 2)
    if mid <= lo or mid >= hi:
        yield from _publisher_buckets(f)
        return
    yield from _price_buckets(base, lo, mid)
    yield from _price_buckets(base, mid, hi)


def _us_hit_to_game(h: dict) -> dict | None:
    nsuid = str(h.get("nsuid") or "")
    # mobile titles carry nsuid "MOBILE" and are not sold on the eShop
    if not nsuid.isdigit() or h.get("platform") == "iOS / Android":
        return None
    img = h.get("productImage") or ""
    if img and not img.startswith("http"):
        img = "https://assets.nintendo.com/image/upload/" + img.lstrip("/")
    return {
        "nsuid": str(nsuid),
        "region": "us",
        "title": (h.get("title") or "").replace("™", "").strip(),
        "publisher": h.get("softwarePublisher") or h.get("softwareDeveloper") or "",
        "release_date": (h.get("releaseDate") or "")[:10],
        "product_code": "",
        "platform": h.get("platform") or "Nintendo Switch",
        "image_url": img,
        "url": ("https://www.nintendo.com" + h["url"]) if h.get("url") else "",
    }


def fetch_us(progress: Progress = _noop, include_dlc: bool = False) -> Iterator[dict]:
    base = "" if include_dlc else 'NOT topLevelFilters:"DLC"'
    seen: set[str] = set()
    done = 0

    def emit(hits):
        nonlocal done
        for h in hits:
            g = _us_hit_to_game(h)
            if g and g["nsuid"] not in seen:
                seen.add(g["nsuid"])
                done += 1
                yield g

    # 1) titles without a numeric price (free-to-start etc.) via the facet
    free_filter = (base + " AND " if base else "") + 'priceRange:"Free to start"'
    yield from emit(_algolia_all(free_filter))
    progress(f"US: {done} (free)")

    # 2) everything else, sliced by regular price so that no slice exceeds
    #    Algolia's 1000-hit pagination limit
    priced_base = base or "price.regPrice >= 0"
    for bucket in _price_buckets(priced_base, 0, 1000):
        yield from emit(_algolia_all(bucket))
        progress(f"US: {done}")


# ---------------------------------------------------------------------------
# Japan  (search.nintendo.jp)
# ---------------------------------------------------------------------------

JP_SEARCH = "https://search.nintendo.jp/nintendo_soft/search.json"
JP_HARDWARE = {"1_HAC": "Nintendo Switch", "05_BEE": "Nintendo Switch 2"}
JP_GAME_SFORMS = ("HAC_DL", "HAC_DOWNLOADABLE", "HAC_CARD")
JP_PAGE = 300
_JP_DATE = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})")


def _jp_date(s: str | None) -> str:
    m = _JP_DATE.match(s or "")
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def fetch_jp(progress: Progress = _noop, include_dlc: bool = False) -> Iterator[dict]:
    seen: set[str] = set()
    sforms = JP_GAME_SFORMS + (("DLC", "DL_DLC") if include_dlc else ())
    for hard, platform in JP_HARDWARE.items():
        for sform in sforms:
            page = 1
            while True:
                data = get_json(JP_SEARCH, params={
                    "opt_hard": hard, "opt_sform": sform,
                    "limit": JP_PAGE, "page": page,
                })
                result = data["result"]
                items = result.get("items") or []
                if not items:
                    break
                for it in items:
                    nsuid = it.get("nsuid")
                    if not nsuid or nsuid in seen:
                        continue
                    seen.add(nsuid)
                    iurl = it.get("iurl") or ""
                    yield {
                        "nsuid": str(nsuid),
                        "region": "jp",
                        "title": (it.get("title") or "").strip(),
                        "publisher": it.get("maker") or "",
                        "release_date": _jp_date(it.get("sdate")),
                        "product_code": it.get("icode") or "",
                        "platform": platform,
                        "image_url": f"https://img-eshop.cdn.nintendo.net/i/{iurl}.jpg" if iurl else "",
                        "url": f"https://store-jp.nintendo.com/list/software/{nsuid}.html",
                    }
                progress(f"JP {hard}/{sform}: page {page} ({len(seen)} total)")
                if page * JP_PAGE >= result.get("total", 0):
                    break
                page += 1


FETCHERS = {"eu": fetch_eu, "us": fetch_us, "jp": fetch_jp}
