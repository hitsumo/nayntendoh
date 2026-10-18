"""SQLite storage.

Tables
------
games           one row per NSUID (per regional catalog)
prices          compact price history: a new row is written only when the
                price/status of a (nsuid, country) pair changes; otherwise the
                existing row's `last_seen` is bumped. `first_seen`/`last_seen`
                therefore bracket the period during which that price was valid.
fx_rates        cached currency conversion rates
"""

from __future__ import annotations

import difflib
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Iterable

DEFAULT_DB = os.environ.get("ESHOP_DB", os.path.join(os.getcwd(), "eshop.sqlite3"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    nsuid        TEXT PRIMARY KEY,
    region       TEXT NOT NULL,
    title        TEXT NOT NULL,
    publisher    TEXT DEFAULT '',
    release_date TEXT DEFAULT '',
    product_code TEXT DEFAULT '',
    code_core    TEXT DEFAULT '',
    platform     TEXT DEFAULT '',
    image_url    TEXT DEFAULT '',
    url          TEXT DEFAULT '',
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_games_region ON games(region);
CREATE INDEX IF NOT EXISTS idx_games_title  ON games(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_games_code   ON games(code_core);

CREATE TABLE IF NOT EXISTS prices (
    id                  INTEGER PRIMARY KEY,
    nsuid               TEXT NOT NULL,
    country             TEXT NOT NULL,
    sales_status        TEXT NOT NULL,
    currency            TEXT DEFAULT '',
    regular_price       REAL,
    regular_price_text  TEXT DEFAULT '',
    discount_price      REAL,
    discount_price_text TEXT DEFAULT '',
    discount_start      TEXT DEFAULT '',
    discount_end        TEXT DEFAULT '',
    first_seen          TEXT NOT NULL,
    last_seen           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prices_key ON prices(nsuid, country, last_seen);
CREATE INDEX IF NOT EXISTS idx_prices_country ON prices(country, last_seen);

CREATE TABLE IF NOT EXISTS fx_rates (
    base       TEXT NOT NULL,
    quote      TEXT NOT NULL,
    rate       REAL NOT NULL,
    fetched_at TEXT NOT NULL,
    rate_date  TEXT DEFAULT '',
    PRIMARY KEY (base, quote)
);

-- latest price row per (nsuid, country)
CREATE VIEW IF NOT EXISTS latest_prices AS
SELECT p.*
FROM prices p
JOIN (SELECT nsuid, country, MAX(last_seen) AS last_seen
      FROM prices GROUP BY nsuid, country) m
  ON m.nsuid = p.nsuid AND m.country = p.country AND m.last_seen = p.last_seen;
"""

PRICE_FIELDS = ("sales_status", "currency", "regular_price", "regular_price_text",
                "discount_price", "discount_price_text", "discount_start", "discount_end")


def code_core(product_code: str) -> str:
    """Normalise a product code so that EU 'HACPAXN7A' and JP 'AXN7A' match.

    Full codes look like HAC P AXN7A (platform, media, 5-char title id);
    the Japanese store only exposes the 5-char title id.
    """
    code = (product_code or "").strip().upper()
    if len(code) == 9 and code.startswith(("HAC", "BEE")):
        return code[4:9]
    if len(code) == 5:
        return code
    return ""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: str = DEFAULT_DB):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        """Add columns introduced after the first release to older databases."""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(fx_rates)")}
        if "rate_date" not in cols:
            with self.conn:
                self.conn.execute("ALTER TABLE fx_rates ADD COLUMN rate_date TEXT DEFAULT ''")

    def close(self):
        self.conn.close()

    # -- games -------------------------------------------------------------

    def upsert_games(self, games: Iterable[dict]) -> int:
        ts = now()
        rows = [(g["nsuid"], g["region"], g["title"], g.get("publisher", ""),
                 g.get("release_date", ""), g.get("product_code", ""),
                 code_core(g.get("product_code", "")),
                 g.get("platform", ""), g.get("image_url", ""), g.get("url", ""), ts, ts)
                for g in games]
        with self.conn:
            self.conn.executemany("""
                INSERT INTO games (nsuid, region, title, publisher, release_date,
                                   product_code, code_core, platform, image_url, url,
                                   first_seen, last_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(nsuid) DO UPDATE SET
                    title=excluded.title, publisher=excluded.publisher,
                    release_date=excluded.release_date,
                    product_code=CASE WHEN excluded.product_code != '' THEN excluded.product_code ELSE games.product_code END,
                    code_core=CASE WHEN excluded.code_core != '' THEN excluded.code_core ELSE games.code_core END,
                    platform=excluded.platform, image_url=excluded.image_url,
                    url=excluded.url, last_seen=excluded.last_seen
            """, rows)
        return len(rows)

    def game_count(self, region: str | None = None) -> int:
        if region:
            return self.conn.execute("SELECT COUNT(*) FROM games WHERE region=?", (region,)).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

    def nsuids(self, region: str, search: str | None = None) -> list[str]:
        sql = "SELECT nsuid FROM games WHERE region=?"
        args: list = [region]
        if search:
            sql += " AND title LIKE ? COLLATE NOCASE"
            args.append(f"%{search}%")
        return [r[0] for r in self.conn.execute(sql, args)]

    def search_games(self, text: str, region: str | None = None, limit: int = 50) -> list[sqlite3.Row]:
        sql = "SELECT * FROM games WHERE (title LIKE ? COLLATE NOCASE OR nsuid = ? OR product_code = ?)"
        args: list = [f"%{text}%", text, text]
        if region:
            sql += " AND region=?"
            args.append(region)
        sql += " ORDER BY title COLLATE NOCASE LIMIT ?"
        args.append(limit)
        return self.conn.execute(sql, args).fetchall()

    def related_games(self, nsuid: str) -> list[sqlite3.Row]:
        """The game itself plus its counterparts in other regional catalogs
        (linked through the shared 5-character title code when available)."""
        g = self.get_game(nsuid)
        if not g:
            return []
        if g["code_core"]:
            return self.conn.execute(
                "SELECT * FROM games WHERE nsuid=? OR code_core=? ORDER BY region",
                (nsuid, g["code_core"])).fetchall()
        return [g]

    def get_game(self, nsuid: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM games WHERE nsuid=?", (nsuid,)).fetchone()

    _words: set[str] | None = None

    def suggest(self, text: str) -> str | None:
        """Spelling suggestion for a failed title search ('oddysey' -> 'odyssey').

        Each query word that does not occur in any title is replaced by the
        closest word that does. Returns the corrected query, or None when
        nothing better was found."""
        if self._words is None:
            words: set[str] = set()
            for (title,) in self.conn.execute("SELECT title FROM games"):
                words.update(re.findall(r"[^\W_]+", title.lower()))
            self._words = words
        out, changed = [], False
        for w in text.split():
            lw = w.lower()
            if lw in self._words or len(lw) < 3:
                out.append(w)
                continue
            match = difflib.get_close_matches(lw, self._words, n=1, cutoff=0.75)
            if match:
                out.append(match[0])
                changed = True
            else:
                out.append(w)
        return " ".join(out) if changed else None

    # -- prices ------------------------------------------------------------

    def record_prices(self, entries: Iterable[dict]) -> tuple[int, int]:
        """Store price observations. Returns (new_rows, refreshed_rows)."""
        ts = now()
        new = refreshed = 0
        cur = self.conn.cursor()
        with self.conn:
            for e in entries:
                last = cur.execute("""
                    SELECT id, sales_status, currency, regular_price, regular_price_text,
                           discount_price, discount_price_text, discount_start, discount_end
                    FROM prices WHERE nsuid=? AND country=?
                    ORDER BY last_seen DESC LIMIT 1
                """, (e["nsuid"], e["country"])).fetchone()
                if last and all(last[f] == e.get(f) for f in PRICE_FIELDS):
                    cur.execute("UPDATE prices SET last_seen=? WHERE id=?", (ts, last["id"]))
                    refreshed += 1
                else:
                    cur.execute("""
                        INSERT INTO prices (nsuid, country, sales_status, currency,
                            regular_price, regular_price_text, discount_price,
                            discount_price_text, discount_start, discount_end,
                            first_seen, last_seen)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (e["nsuid"], e["country"], e["sales_status"], e.get("currency", ""),
                          e.get("regular_price"), e.get("regular_price_text", ""),
                          e.get("discount_price"), e.get("discount_price_text", ""),
                          e.get("discount_start", ""), e.get("discount_end", ""), ts, ts))
                    new += 1
        return new, refreshed

    def list_prices(self, country: str, *, search: str | None = None,
                    status: str | None = "onsale", on_sale_only: bool = False,
                    sort: str = "title", limit: int | None = None,
                    platform: str | None = None) -> list[sqlite3.Row]:
        sql = """
            SELECT g.nsuid, g.title, g.publisher, g.release_date, g.platform, g.url,
                   p.country, p.sales_status, p.currency, p.regular_price, p.regular_price_text,
                   p.discount_price, p.discount_price_text, p.discount_start, p.discount_end,
                   p.first_seen, p.last_seen,
                   COALESCE(p.discount_price, p.regular_price) AS effective_price
            FROM latest_prices p JOIN games g ON g.nsuid = p.nsuid
            WHERE p.country = ?
        """
        args: list = [country]
        if status:
            sql += " AND p.sales_status = ?"
            args.append(status)
        if on_sale_only:
            sql += " AND p.discount_price IS NOT NULL"
        if search:
            sql += " AND g.title LIKE ? COLLATE NOCASE"
            args.append(f"%{search}%")
        if platform:
            sql += " AND g.platform LIKE ?"
            args.append(f"%{platform}%")
        order = {
            "title": "g.title COLLATE NOCASE ASC",
            "price": "effective_price ASC, g.title COLLATE NOCASE",
            "price_desc": "effective_price DESC, g.title COLLATE NOCASE",
            "date": "g.release_date DESC, g.title COLLATE NOCASE",
            "discount": "(1.0 - p.discount_price / NULLIF(p.regular_price, 0)) DESC, g.title COLLATE NOCASE",
            "updated": "p.last_seen DESC, g.title COLLATE NOCASE",
        }[sort]
        sql += f" ORDER BY {order}"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        return self.conn.execute(sql, args).fetchall()

    def latest_price(self, nsuid: str, country: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM latest_prices WHERE nsuid=? AND country=?", (nsuid, country)).fetchone()

    def latest_prices_for(self, nsuid: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM latest_prices WHERE nsuid=? ORDER BY country", (nsuid,)).fetchall()

    def price_history(self, nsuid: str, country: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM prices WHERE nsuid=?"
        args: list = [nsuid]
        if country:
            sql += " AND country=?"
            args.append(country)
        sql += " ORDER BY country, first_seen"
        return self.conn.execute(sql, args).fetchall()

    def countries_with_prices(self) -> list[tuple[str, int, str]]:
        return [tuple(r) for r in self.conn.execute("""
            SELECT country, COUNT(*), MAX(last_seen) FROM latest_prices
            GROUP BY country ORDER BY country""")]

    # -- fx ----------------------------------------------------------------

    def get_fx(self, base: str, quote: str):
        return self.conn.execute(
            "SELECT rate, fetched_at FROM fx_rates WHERE base=? AND quote=?", (base, quote)).fetchone()

    def set_fx(self, base: str, rates: dict[str, float], rate_date: str = ""):
        ts = now()
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO fx_rates (base, quote, rate, fetched_at, rate_date) VALUES (?,?,?,?,?)",
                [(base, q, r, ts, rate_date) for q, r in rates.items()])
