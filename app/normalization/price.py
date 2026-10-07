"""Normalizacion de precios.

Los sitios exponen el precio como texto libre ("$29.99", "USD 1.234,50", "15.99").
El challenge pide almacenar los datos normalizados, asi que ademas del texto original
guardamos monto decimal y moneda en columnas tipadas.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_CURRENCY_BY_SYMBOL = {
    "$": "USD",
    "US$": "USD",
    "usd": "USD",
    "\u20ac": "EUR",
    "eur": "EUR",
    "\u00a3": "GBP",
    "gbp": "GBP",
    "mxn": "MXN",
    "ars": "ARS",
}

_NUMBER_RE = re.compile(r"\d[\d.,\s\u00a0]*\d|\d")


@dataclass(frozen=True)
class ParsedPrice:
    """Resultado de normalizar un precio: el texto original mas sus partes tipadas."""

    text: str
    amount: Decimal | None
    currency: str | None


def _detect_currency(raw: str) -> str | None:
    lowered = raw.lower()
    for token, code in sorted(_CURRENCY_BY_SYMBOL.items(), key=lambda kv: -len(kv[0])):
        if token.lower() in lowered:
            return code
    return None


def _to_decimal(number: str) -> Decimal | None:
    """Convierte un numero con separadores ambiguos a Decimal.

    Decide si el ultimo separador es decimal o de miles por la cantidad de digitos que
    lo siguen: "1.234" son mil doscientos treinta y cuatro; "12.34", doce con treinta y cuatro.
    """
    cleaned = re.sub(r"[\s\u00a0]", "", number)
    if not cleaned:
        return None

    last_sep = max(cleaned.rfind("."), cleaned.rfind(","))
    if last_sep == -1:
        integer, fraction = cleaned, ""
    else:
        decimals = cleaned[last_sep + 1 :]
        if len(decimals) in (1, 2) and decimals.isdigit():
            integer, fraction = cleaned[:last_sep], decimals
        else:
            integer, fraction = cleaned, ""

    integer = re.sub(r"[.,]", "", integer)
    if not integer.isdigit():
        return None

    try:
        return Decimal(f"{integer}.{fraction}" if fraction else integer)
    except InvalidOperation:
        return None


def parse_price(raw: str | None) -> ParsedPrice:
    """Normaliza un precio en texto libre. Nunca lanza: si no puede parsear devuelve None."""
    text = (raw or "").strip()
    if not text:
        return ParsedPrice(text="", amount=None, currency=None)

    match = _NUMBER_RE.search(text)
    amount = _to_decimal(match.group(0)) if match else None
    currency = _detect_currency(text)

    if amount is not None and currency is None:
        currency = "USD"

    return ParsedPrice(text=text, amount=amount, currency=currency)
