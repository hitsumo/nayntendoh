"""Update check against the GitHub releases of this project.

The check is cheap (one small request, 3 s timeout) and the answer is cached
in the database for a few hours so that starting the program repeatedly does
not keep hitting GitHub. Any failure (offline, rate limit) is silent.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone

from . import __version__
from .db import Database
from .http import get_json

REPO = "hitsumo/nayntendoh"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
CACHE_TTL = timedelta(hours=6)

ASSET_FOR_PLATFORM = {
    "win32": "eshop-windows-x64.zip",
    "darwin": "eshop-macos-arm64.zip",
    "linux": "eshop-linux-x64.zip",
}


def _parse(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def _fetch() -> dict | None:
    data = get_json(LATEST_URL, timeout=3, retries=0,
                    headers={"Accept": "application/vnd.github+json"})
    tag = data.get("tag_name") or ""
    if not tag:
        return None
    wanted = ASSET_FOR_PLATFORM.get(sys.platform, "")
    asset = next((a["browser_download_url"] for a in data.get("assets", [])
                  if a.get("name") == wanted), None)
    return {
        "version": tag.lstrip("v"),
        "page": data.get("html_url") or RELEASES_PAGE,
        "asset": asset or data.get("html_url") or RELEASES_PAGE,
        "published": (data.get("published_at") or "")[:10],
    }


def check(db: Database, force: bool = False) -> dict | None:
    """Return info about the latest release, or None if unknown.

    The result dict has: version, page, asset, published, is_newer."""
    cached = db.get_meta("latest_release")
    info = None
    if cached and not force:
        try:
            payload = json.loads(cached)
            fetched = datetime.fromisoformat(payload["fetched_at"])
            if datetime.now(timezone.utc) - fetched < CACHE_TTL:
                info = payload["info"]
        except (KeyError, ValueError, TypeError):
            info = None
    if info is None:
        try:
            info = _fetch()
        except Exception:
            info = None
        if info:
            db.set_meta("latest_release", json.dumps({
                "fetched_at": datetime.now(timezone.utc).isoformat(), "info": info}))
    if not info:
        return None
    info = dict(info)
    info["is_newer"] = _parse(info["version"]) > _parse(__version__)
    return info


def notice(info: dict | None) -> str:
    """Short Turkish status line for the menu / CLI."""
    if not info:
        return ""
    if info["is_newer"]:
        return (f"Yeni sürüm var: {info['version']} (sizdeki: {__version__}). "
                f"İndirmek için 'u' yazın veya: {info['asset']}")
    return f"Yazılım güncel ({__version__})."
