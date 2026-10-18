"""Country / region metadata.

Nintendo runs three separate eShop catalogs (Americas, Europe, Japan). A game
has a different NSUID in each catalog, and the price API only knows the NSUIDs
of the catalog a country belongs to. So each supported country is mapped to
the catalog ("region") whose NSUIDs must be used when asking for its prices.
"""

REGIONS = {
    "us": "Americas",
    "eu": "Europe / Oceania / Africa",
    "jp": "Japan",
}

# code -> (region, name, currency)
COUNTRIES = {
    # Americas catalog
    "US": ("us", "United States", "USD"),
    "CA": ("us", "Canada", "CAD"),
    "MX": ("us", "Mexico", "MXN"),
    "BR": ("us", "Brazil", "BRL"),
    "AR": ("us", "Argentina", "ARS"),
    "CL": ("us", "Chile", "CLP"),
    "CO": ("us", "Colombia", "COP"),
    "PE": ("us", "Peru", "PEN"),
    # European catalog (also used by Oceania, South Africa and Russia)
    "AT": ("eu", "Austria", "EUR"),
    "BE": ("eu", "Belgium", "EUR"),
    "BG": ("eu", "Bulgaria", "EUR"),
    "CH": ("eu", "Switzerland", "CHF"),
    "CY": ("eu", "Cyprus", "EUR"),
    "CZ": ("eu", "Czechia", "CZK"),
    "DE": ("eu", "Germany", "EUR"),
    "DK": ("eu", "Denmark", "DKK"),
    "EE": ("eu", "Estonia", "EUR"),
    "ES": ("eu", "Spain", "EUR"),
    "FI": ("eu", "Finland", "EUR"),
    "FR": ("eu", "France", "EUR"),
    "GB": ("eu", "United Kingdom", "GBP"),
    "GR": ("eu", "Greece", "EUR"),
    "HR": ("eu", "Croatia", "EUR"),
    "HU": ("eu", "Hungary", "HUF"),
    "IE": ("eu", "Ireland", "EUR"),
    "IT": ("eu", "Italy", "EUR"),
    "LT": ("eu", "Lithuania", "EUR"),
    "LU": ("eu", "Luxembourg", "EUR"),
    "LV": ("eu", "Latvia", "EUR"),
    "MT": ("eu", "Malta", "EUR"),
    "NL": ("eu", "Netherlands", "EUR"),
    "NO": ("eu", "Norway", "NOK"),
    "PL": ("eu", "Poland", "PLN"),
    "PT": ("eu", "Portugal", "EUR"),
    "RO": ("eu", "Romania", "RON"),
    "RU": ("eu", "Russia", "RUB"),
    "SE": ("eu", "Sweden", "SEK"),
    "SI": ("eu", "Slovenia", "EUR"),
    "SK": ("eu", "Slovakia", "EUR"),
    "ZA": ("eu", "South Africa", "ZAR"),
    "AU": ("eu", "Australia", "AUD"),
    "NZ": ("eu", "New Zealand", "NZD"),
    # Japan catalog
    "JP": ("jp", "Japan", "JPY"),
}

# Countries that have no eShop of their own. Kept here so the CLI can give a
# helpful message instead of silently returning nothing.
NO_ESHOP = {
    "TR": "Turkey has no official Nintendo eShop; the price API reports every "
          "title as not_found. Turkish players typically use another region's "
          "store (e.g. a European country).",
}


def region_of(country: str) -> str:
    country = country.upper()
    if country in NO_ESHOP:
        raise ValueError(NO_ESHOP[country])
    try:
        return COUNTRIES[country][0]
    except KeyError:
        raise ValueError(f"Unknown country code {country!r}. "
                         f"Run `eshop countries` for the supported list.") from None


def currency_of(country: str) -> str:
    return COUNTRIES[country.upper()][2]


def countries_in_region(region: str):
    return sorted(c for c, (r, _, _) in COUNTRIES.items() if r == region)
