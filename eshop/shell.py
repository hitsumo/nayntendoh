"""Interactive mode, used when the program is started without arguments
(e.g. by double-clicking eshop.exe). Keeps the console window open and
offers a simple menu plus a prompt where any normal CLI command can be
typed."""

from __future__ import annotations

import shlex
import sys

from . import __version__
from .db import DEFAULT_DB, Database
from .regions import COUNTRIES, NO_ESHOP

MENU = """
┌─ eshop {ver} ─ Nintendo Switch eShop ülke / fiyat takipçisi ─────────────────┐
│ 1  Katalogları indir            (catalog)         ilk kullanımda gerekli, 5-8 dk │
│ 2  Fiyatları güncelle           (prices)          ülke başına ~1 dk              │
│ 3  Ülkedeki oyunları listele    (list)                                           │
│ 4  Sadece indirimdekiler        (list --on-sale)                                 │
│ 5  Oyun ara + fiyatına bak      (search, compare)                                │
│ 6  Ülkeler arası karşılaştır    (compare)                                        │
│ 7  Fiyat geçmişi                (history)                                        │
│ 8  Veritabanı durumu            (status)                                         │
│ 9  Desteklenen ülkeler          (countries)                                      │
│ ?  Bir komutun yardımı          (örn: ? list)                                    │
│ 0  Çıkış                                                                         │
└──────────────────────────────────────────────────────────────────────────────────┘
İstersen menü numarası yerine doğrudan komut da yazabilirsin:
  list --country DE --on-sale --sort discount --convert TRY
"""


def _ask(prompt: str, default: str = "") -> str:
    try:
        v = input(f"{prompt}{' [' + default + ']' if default else ''}: ").strip()
    except EOFError:
        raise KeyboardInterrupt
    return v or default


def _ask_countries(prompt="Ülke kodları (boşlukla ayır, örn: DE GB US JP)", default="DE") -> list[str]:
    while True:
        raw = _ask(prompt, default).upper().replace(",", " ").split()
        from .cli import REGION_ALIASES
        bad = [c for c in raw if c not in COUNTRIES and c not in REGION_ALIASES and c != "ALL"]
        if not bad:
            return raw
        for c in bad:
            print(f"  {c}: " + NO_ESHOP.get(c, "bilinmeyen ülke kodu (liste için 9)"))


SORTS = {"1": "price", "2": "price_desc", "3": "game", "4": "country", "5": "discount"}


def _ask_sort() -> str:
    v = _ask("Sıralama: 1 ucuzdan pahalıya, 2 pahalıdan ucuza, 3 oyuna göre, 4 ülkeye göre, 5 indirim oranı", "1")
    return SORTS.get(v, v if v in SORTS.values() else "price")


def _build(choice: str) -> list[str] | None:
    """Turn a menu choice into CLI arguments, asking for the details."""
    if choice == "1":
        return ["catalog"]
    if choice == "2":
        return ["prices", "--country", *_ask_countries()]
    if choice in ("3", "4"):
        args = ["list", "--country", _ask_countries("Ülke kodu", "DE")[0]]
        if choice == "4":
            args.append("--on-sale")
        s = _ask("Başlıkta ara (boş = hepsi)")
        if s:
            args += ["--search", s]
        sort = _ask("Sıralama: title / price / price_desc / date / discount / updated",
                    "discount" if choice == "4" else "title")
        args += ["--sort", sort]
        cur = _ask("Çevrilecek para birimi (boş = yok, örn: TRY)")
        if cur:
            args += ["--convert", cur.upper()]
        lim = _ask("En fazla kaç satır", "50")
        if lim.isdigit():
            args += ["--limit", lim]
        return args
    if choice == "5":
        return ["search", _ask("Aranacak metin")]
    if choice == "6":
        args = ["compare", _ask("Oyun adı veya NSUID")]
        countries = _ask_countries("Ülkeler", "DE GB PL US JP")
        args += ["--country", *countries]
        if _ask("Fiyatlar şimdi taze çekilsin mi? (e/h)", "e").lower().startswith("e"):
            args.append("--fetch")
        cur = _ask("Çevrilecek para birimi", "TRY")
        if cur:
            args += ["--convert", cur.upper()]
        args += ["--sort", _ask_sort()]
        return args
    if choice == "7":
        args = ["history", _ask("NSUID")]
        c = _ask("Ülke kodu (boş = hepsi)")
        if c:
            args += ["--country", c.upper()]
        return args
    if choice == "8":
        return ["status"]
    if choice == "9":
        return ["countries"]
    return None


def run(main) -> int:
    """Interactive loop. `main` is the normal CLI entry point."""
    print(MENU.format(ver=__version__))
    while True:
        try:
            line = input("eshop> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("0", "q", "quit", "exit", "çıkış", "cikis"):
            return 0
        if line in ("m", "menu", "menü", "h", "help", "?"):
            print(MENU.format(ver=__version__))
            continue
        if line.startswith("?"):
            argv = [line[1:].strip(), "--help"]
        elif line.isdigit():
            try:
                argv = _build(line)
            except KeyboardInterrupt:
                print()
                continue
            if argv is None:
                print("  Geçersiz seçim. Menü için 'm' yaz.")
                continue
            print("  > eshop " + " ".join(shlex.quote(a) for a in argv))
        else:
            try:
                argv = shlex.split(line)
            except ValueError as exc:
                print(f"  Hatalı komut: {exc}")
                continue
            if argv and argv[0] == "eshop":
                argv = argv[1:]
        code = _run(main, argv)
        if line == "5" and argv and argv[0] == "search":
            text = argv[1]
            if code != 0:
                text = _retry_with_suggestion(main, text)
            if text:
                _prices_after_search(main, text)
            else:
                print("  Sonuç yok, menüye dönülüyor.")
        print()


def _run(main, argv: list[str]) -> int:
    """Run one CLI command; returns its exit code (non-zero = no result/error)."""
    try:
        return int(main(argv) or 0)
    except SystemExit as exc:
        return int(exc.code or 0) if isinstance(exc.code, int) else 1
    except KeyboardInterrupt:
        print("\n  iptal edildi")
        return 130
    except Exception as exc:  # keep the window alive on unexpected errors
        print(f"  hata: {exc}", file=sys.stderr)
        return 1


def _retry_with_suggestion(main, text: str) -> str | None:
    """After an empty search, offer the spelling suggestion. Returns the text
    that produced results, or None."""
    try:
        db = Database(DEFAULT_DB)
        try:
            hint = db.suggest(text)
        finally:
            db.close()
        if not hint:
            return None
        if not _ask(f"'{hint}' ile tekrar aransın mı? (e/h)", "e").lower().startswith("e"):
            return None
    except KeyboardInterrupt:
        print()
        return None
    print("  > eshop search " + shlex.quote(hint))
    return hint if _run(main, ["search", hint]) == 0 else None


def _prices_after_search(main, text: str) -> None:
    """After a catalog search, offer to look the prices up right away."""
    print()
    try:
        raw = _ask("Fiyatlarına bakmak için ülke kodları yaz (boş = geç). Örn: DE GB US JP, tüm Avrupa için EU, hepsi için ALL")
        if not raw:
            return
        countries = raw.upper().replace(",", " ").split()
        cur = _ask("Çevrilecek para birimi", "TRY")
    except KeyboardInterrupt:
        print()
        return
    argv = ["compare", text, "--country", *countries, "--fetch"]
    if cur:
        argv += ["--convert", cur.upper()]
    try:
        argv += ["--sort", _ask_sort()]
    except KeyboardInterrupt:
        print()
        return
    print("  > eshop " + " ".join(shlex.quote(a) for a in argv))
    _run(main, argv)
