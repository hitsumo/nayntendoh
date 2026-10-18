"""Currency conversion via the free Frankfurter API (ECB reference rates).

Rates are cached in the database for a day. Currencies the ECB does not
publish (ARS, CLP, COP, PEN, RUB, ...) cannot be converted and return None.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .db import Database
from .http import get_json

FRANKFURTER = "https://api.frankfurter.app/latest"
CACHE_TTL = timedelta(hours=24)


class Converter:
    def __init__(self, db: Database, target: str):
        self.db = db
        self.target = target.upper()
        self._rates: dict[str, float] | None = None
        self._failed = False

    def _load(self) -> dict[str, float]:
        if self._rates is not None:
            return self._rates
        cached = self.db.get_fx(self.target, self.target)
        fresh = False
        if cached:
            fetched = datetime.fromisoformat(cached["fetched_at"])
            fresh = datetime.now(timezone.utc) - fetched < CACHE_TTL
        if not fresh and not self._failed:
            try:
                data = get_json(FRANKFURTER, params={"from": self.target})
                rates = {k.upper(): float(v) for k, v in data.get("rates", {}).items()}
                rates[self.target] = 1.0
                self.db.set_fx(self.target, rates)
            except Exception:
                self._failed = True
        rows = self.db.conn.execute(
            "SELECT quote, rate FROM fx_rates WHERE base=?", (self.target,)).fetchall()
        self._rates = {r["quote"]: r["rate"] for r in rows}
        return self._rates

    def convert(self, amount: float | None, currency: str) -> float | None:
        """Convert `amount` of `currency` into the target currency."""
        if amount is None or not currency:
            return None
        rates = self._load()
        rate = rates.get(currency.upper())
        if not rate:
            return None
        # rates are target -> currency, so divide
        return amount / rate
