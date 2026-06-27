"""Canonicalization maps for the cleaning pipeline."""

from __future__ import annotations

# Curated alias map for provider display names (canonical slug → display name).
_PROVIDER_ALIAS_MAP: dict[str, str] = {
    "hsbc": "HSBC",
    "bank-of-america": "Bank of America",
    "chase": "Chase",
    "wells-fargo": "Wells Fargo",
    "citibank": "Citibank",
    "capital-one": "Capital One",
    "pnc-bank": "PNC Bank",
    "td-bank": "TD Bank",
    "us-bancorp": "US Bancorp",
    "truist": "Truist",
}

# Currency normalization map (lowercase stripped → ISO code).
_CURRENCY_MAP: dict[str, str] = {
    "usd": "USD",
    "us dollar": "USD",
    "usd ": "USD",
    "eur": "EUR",
    "euro": "EUR",
    "gbp": "GBP",
    "pound": "GBP",
}

FUTURE_DATE_TOLERANCE_DAYS = 30
