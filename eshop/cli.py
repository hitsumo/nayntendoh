"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from . import __version__
from .catalog import FETCHERS
from .db import DEFAULT_DB, Database
from .fx import Converter
from .prices import fetch_prices
from .regions import COUNTRIES, NO_ESHOP, REGIONS, currency_of, region_of
from .table import render, write_csv, write_json

WRITERS = {"table": render, "csv": write_csv, "json": write_json}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def progress_line(msg: str) -> None:
    print("\r\033[K" + msg, end="", file=sys.stderr, flush=True)


def fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso[:16]


def fmt_pct(regular, discount) -> str:
    if regular and discount is not None and regular > 0:
        return f"-{round((1 - discount / regular) * 100)}%"
    return ""


def fmt_money(value: float | None, currency: str) -> str:
    if value is None:
        return ""
    if currency in ("JPY", "HUF", "CLP", "COP", "KRW"):
        return f"{value:,.0f} {currency}"
    return f"{value:,.2f} {currency}"


def parse_countries(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        for c in v.replace(",", " ").split():
            c = c.upper()
            if c == "ALL":
                out.extend(COUNTRIES)
            elif c in REGIONS:
                out.extend(k for k, (r, _, _) in COUNTRIES.items() if r == c)
            else:
                region_of(c)  # validates, raises for unknown / no-eshop
                out.append(c)
    return list(dict.fromkeys(out))


def emit(args, headers, rows, numeric=()):
    writer = WRITERS[args.format]
    out = open(args.output, "w", encoding="utf-8", newline="") if getattr(args, "output", None) else None
    try:
        if args.format == "table":
            writer(headers, rows, numeric=numeric, file=out)
        else:
            writer(headers, rows, file=out)
    finally:
        if out:
            out.close()
            log(f"Wrote {len(rows)} rows to {args.output}")


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_countries(args, db: Database) -> int:
    have = {c: (n, ts) for c, n, ts in db.countries_with_prices()}
    rows = []
    for code, (region, name, cur) in sorted(COUNTRIES.items(), key=lambda kv: (kv[1][0], kv[0])):
        n, ts = have.get(code, (0, ""))
        rows.append([code, name, cur, region, REGIONS[region], n or "", fmt_date(ts)])
    render(["Code", "Country", "Currency", "Catalog", "Catalog name", "Prices stored", "Last update"],
           rows, numeric=(5,))
    print()
    for code, why in NO_ESHOP.items():
        print(f"{code}: {why}")
    return 0


def cmd_catalog(args, db: Database) -> int:
    regions = args.region or list(FETCHERS)
    for region in regions:
        fetch = FETCHERS[region]
        log(f"Fetching {REGIONS[region]} catalog…")
        kwargs = {"progress": progress_line}
        if region in ("us", "jp"):
            kwargs["include_dlc"] = args.include_dlc
        count = 0
        batch: list[dict] = []
        for game in fetch(**kwargs):
            batch.append(game)
            if len(batch) >= 500:
                count += db.upsert_games(batch)
                batch.clear()
        count += db.upsert_games(batch)
        progress_line("")
        log(f"{region.upper()}: {count} titles stored (total in catalog now {db.game_count(region)})")
    return 0


def _update_prices(db: Database, countries: list[str], search: str | None, workers: int) -> None:
    for country in countries:
        region = region_of(country)
        ids = db.nsuids(region, search)
        if not ids:
            log(f"{country}: no titles in the {region.upper()} catalog yet - run `eshop catalog --region {region}` first.")
            continue
        log(f"{country}: fetching prices for {len(ids)} titles…")
        entries = fetch_prices(country, ids, workers=workers,
                               progress=lambda d, t: progress_line(f"{country}: {d}/{t} batches"))
        progress_line("")
        new, refreshed = db.record_prices(entries)
        onsale = sum(1 for e in entries if e["sales_status"] == "onsale")
        log(f"{country}: {onsale} on sale, {new} price changes recorded, {refreshed} unchanged")


def cmd_prices(args, db: Database) -> int:
    _update_prices(db, parse_countries(args.country), args.search, args.workers)
    return 0


def cmd_update(args, db: Database) -> int:
    countries = parse_countries(args.country)
    regions = sorted({region_of(c) for c in countries})
    ns = argparse.Namespace(region=regions, include_dlc=args.include_dlc)
    cmd_catalog(ns, db)
    _update_prices(db, countries, None, args.workers)
    return 0


def cmd_list(args, db: Database) -> int:
    country = parse_countries([args.country])[0]
    status = None if args.status == "all" else args.status
    rows = db.list_prices(country, search=args.search, status=status, on_sale_only=args.on_sale,
                          sort=args.sort, limit=args.limit, platform=args.platform)
    conv = Converter(db, args.convert) if args.convert else None
    headers = ["NSUID", "Title", "Platform", "Release", "Status", "Regular", "Discount", "Off",
               "Sale ends", "Price seen"]
    if conv:
        headers.insert(8, f"≈ {conv.target}")
    out = []
    for r in rows:
        row = [r["nsuid"], r["title"], r["platform"].replace("Nintendo ", ""), r["release_date"],
               r["sales_status"], r["regular_price_text"], r["discount_price_text"],
               fmt_pct(r["regular_price"], r["discount_price"]), fmt_date(r["discount_end"]),
               fmt_date(r["last_seen"])]
        if conv:
            v = conv.convert(r["effective_price"], r["currency"])
            row.insert(8, f"{v:,.2f}" if v is not None else "n/a")
        out.append(row)
    if not out:
        log(f"No prices stored for {country}. Run `eshop update --country {country}` first.")
        return 1
    emit(args, headers, out, numeric=(5, 6, 7, 8) if conv else (5, 6, 7))
    return 0


def cmd_search(args, db: Database) -> int:
    rows = db.search_games(args.text, region=args.region, limit=args.limit)
    out = [[g["nsuid"], g["region"].upper(), g["title"], g["publisher"], g["release_date"],
            g["platform"].replace("Nintendo ", ""), g["product_code"]] for g in rows]
    if not out:
        log("No matching titles. Has the catalog been fetched? (`eshop catalog`)")
        return 1
    emit(args, ["NSUID", "Catalog", "Title", "Publisher", "Release", "Platform", "Code"], out)
    return 0


def cmd_compare(args, db: Database) -> int:
    # resolve the query to a set of games (across regional catalogs)
    if args.query.isdigit():
        games = db.related_games(args.query)
    else:
        matches = db.search_games(args.query, limit=args.limit)
        seen: dict[str, object] = {}
        for m in matches:
            for g in db.related_games(m["nsuid"]):
                seen.setdefault(g["nsuid"], g)
        games = list(seen.values())
    if not games:
        log("No matching titles found in the local catalog.")
        return 1

    countries = parse_countries(args.country) if args.country else None
    if args.fetch:
        if not countries:
            log("--fetch needs --country")
            return 2
        for country in countries:
            region = region_of(country)
            ids = [g["nsuid"] for g in games if g["region"] == region]
            if ids:
                db.record_prices(fetch_prices(country, ids))

    conv = Converter(db, args.convert) if args.convert else None
    headers = ["Country", "Catalog", "NSUID", "Title", "Status", "Regular", "Discount", "Off",
               "Sale ends", "Price seen"]
    if conv:
        headers.insert(8, f"≈ {conv.target}")
    rows = []
    for g in games:
        for p in db.latest_prices_for(g["nsuid"]):
            if countries and p["country"] not in countries:
                continue
            eff = p["discount_price"] if p["discount_price"] is not None else p["regular_price"]
            conv_val = conv.convert(eff, p["currency"]) if conv else None
            rows.append((conv_val if conv_val is not None else float("inf"), [
                p["country"], g["region"].upper(), g["nsuid"], g["title"], p["sales_status"],
                p["regular_price_text"], p["discount_price_text"],
                fmt_pct(p["regular_price"], p["discount_price"]),
                *([f"{conv_val:,.2f}" if conv_val is not None else "n/a"] if conv else []),
                fmt_date(p["discount_end"]), fmt_date(p["last_seen"]),
            ]))
    if not rows:
        titles = ", ".join(f"{g['title']} [{g['region'].upper()} {g['nsuid']}]" for g in games)
        log(f"Found {titles} but no stored prices. Add --country XX --fetch to look them up now.")
        return 1
    if conv:
        rows.sort(key=lambda t: t[0])
    emit(args, headers, [r for _, r in rows], numeric=(5, 6, 7, 8) if conv else (5, 6, 7))
    return 0


def cmd_history(args, db: Database) -> int:
    g = db.get_game(args.nsuid)
    if g:
        print(f"{g['title']}  [{g['region'].upper()} {g['nsuid']}]  {g['platform']}  {g['release_date']}")
    rows = db.price_history(args.nsuid, args.country.upper() if args.country else None)
    out = [[p["country"], p["sales_status"], p["regular_price_text"], p["discount_price_text"],
            fmt_pct(p["regular_price"], p["discount_price"]), fmt_date(p["discount_end"]),
            fmt_date(p["first_seen"]), fmt_date(p["last_seen"])] for p in rows]
    if not out:
        log("No price history stored for this NSUID.")
        return 1
    emit(args, ["Country", "Status", "Regular", "Discount", "Off", "Sale ends", "First seen", "Last seen"],
         out, numeric=(2, 3, 4))
    return 0


def cmd_status(args, db: Database) -> int:
    print(f"Database: {db.path}")
    for region, name in REGIONS.items():
        print(f"  {region.upper()} catalog ({name}): {db.game_count(region)} titles")
    rows = db.countries_with_prices()
    if rows:
        print()
        render(["Country", "Titles priced", "Last update"],
               [[c, n, fmt_date(ts)] for c, n, ts in rows], numeric=(1,))
    else:
        print("  no prices stored yet")
    return 0


# ---------------------------------------------------------------------------

def add_output_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--format", choices=WRITERS, default="table", help="output format (default: table)")
    p.add_argument("-o", "--output", help="write output to this file instead of stdout")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="eshop",
                                description="Track Nintendo Switch eShop catalogs and prices per country.")
    p.add_argument("--db", default=DEFAULT_DB, help=f"SQLite file (default: {DEFAULT_DB}, or $ESHOP_DB)")
    p.add_argument("--version", action="version", version=f"eshop {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("countries", help="list supported countries and what is stored for them")
    s.set_defaults(func=cmd_countries)

    s = sub.add_parser("catalog", help="download the game catalog of one or more regions")
    s.add_argument("--region", nargs="*", choices=list(FETCHERS), help="eu, us and/or jp (default: all)")
    s.add_argument("--include-dlc", action="store_true", help="also store DLC entries (US/JP)")
    s.set_defaults(func=cmd_catalog)

    s = sub.add_parser("prices", help="fetch current prices for one or more countries")
    s.add_argument("--country", nargs="+", required=True,
                   help="country codes (DE GB US JP …), a region (eu/us/jp) or 'all'")
    s.add_argument("--search", help="only titles whose name contains this text")
    s.add_argument("--workers", type=int, default=6, help="parallel requests (default 6)")
    s.set_defaults(func=cmd_prices)

    s = sub.add_parser("update", help="catalog + prices in one go")
    s.add_argument("--country", nargs="+", required=True)
    s.add_argument("--include-dlc", action="store_true")
    s.add_argument("--workers", type=int, default=6)
    s.set_defaults(func=cmd_update)

    s = sub.add_parser("list", help="list games and their latest prices in a country")
    s.add_argument("--country", required=True)
    s.add_argument("--search", help="filter by title")
    s.add_argument("--platform", help="filter by platform, e.g. 'Switch 2'")
    s.add_argument("--status", default="onsale",
                   help="sales status to show: onsale (default), unreleased, not_found, sales_termination, all")
    s.add_argument("--on-sale", action="store_true", help="only discounted titles")
    s.add_argument("--sort", choices=["title", "price", "price_desc", "date", "discount", "updated"],
                   default="title")
    s.add_argument("--limit", type=int)
    s.add_argument("--convert", metavar="CUR", help="add a column converted to this currency (e.g. TRY, EUR)")
    add_output_opts(s)
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("search", help="search titles in the local catalog")
    s.add_argument("text")
    s.add_argument("--region", choices=list(FETCHERS))
    s.add_argument("--limit", type=int, default=50)
    add_output_opts(s)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("compare", help="compare one game's price across countries")
    s.add_argument("query", help="title text or NSUID")
    s.add_argument("--country", nargs="*", help="restrict to these countries")
    s.add_argument("--fetch", action="store_true", help="fetch fresh prices for the listed countries first")
    s.add_argument("--convert", metavar="CUR", help="convert all prices to this currency and sort by it")
    s.add_argument("--limit", type=int, default=10, help="max title matches (default 10)")
    add_output_opts(s)
    s.set_defaults(func=cmd_compare)

    s = sub.add_parser("history", help="price history of one NSUID")
    s.add_argument("nsuid")
    s.add_argument("--country")
    add_output_opts(s)
    s.set_defaults(func=cmd_history)

    s = sub.add_parser("status", help="show what the local database contains")
    s.set_defaults(func=cmd_status)
    return p


def _utf8_console() -> None:
    """Windows consoles default to a legacy code page; make sure Japanese and
    accented titles do not crash the output."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    _utf8_console()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        # started without arguments (e.g. double-click): interactive mode
        from .shell import run
        return run(main)
    args = build_parser().parse_args(argv)
    db = Database(args.db)
    try:
        return args.func(args, db)
    except ValueError as exc:
        log(f"error: {exc}")
        return 2
    except KeyboardInterrupt:
        log("\ninterrupted")
        return 130
    finally:
        db.close()
