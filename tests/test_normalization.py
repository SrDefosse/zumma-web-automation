"""Tests de la normalizacion de precios y texto.

Estas funciones son puras, asi que se pueden cubrir sin navegador ni base de datos.
Esa es la razon de haberlas separado del codigo de Playwright.
"""

from decimal import Decimal

import pytest

from app.normalization import clean_text, parse_price, safe_filename


@pytest.mark.parametrize(
    ("raw", "amount", "currency"),
    [
        ("$29.99", Decimal("29.99"), "USD"),
        ("$7.99", Decimal("7.99"), "USD"),
        ("29.99", Decimal("29.99"), "USD"),
        ("USD 14.15", Decimal("14.15"), "USD"),
        ("€1.234,50", Decimal("1234.50"), "EUR"),
        ("£ 9", Decimal("9"), "GBP"),
        ("$1,299.00", Decimal("1299.00"), "USD"),
        ("$ 1 299", Decimal("1299"), "USD"),
        ("$1.234", Decimal("1234"), "USD"),
    ],
)
def test_parse_price_extrae_monto_y_moneda(raw, amount, currency):
    parsed = parse_price(raw)
    assert parsed.amount == amount
    assert parsed.currency == currency


def test_parse_price_conserva_el_texto_original():
    assert parse_price("  $29.99  ").text == "$29.99"


@pytest.mark.parametrize("raw", ["", None, "N/A", "Sin precio", "   "])
def test_parse_price_no_lanza_ante_entradas_invalidas(raw):
    parsed = parse_price(raw)
    assert parsed.amount is None
    assert parsed.currency is None


def test_clean_text_colapsa_espacios_y_saltos():
    assert clean_text("  Sauce   Labs\n\tBackpack  ") == "Sauce Labs Backpack"


def test_clean_text_acepta_vacio():
    assert clean_text(None) == ""
    assert clean_text("") == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Sauce Labs Backpack", "Sauce-Labs-Backpack"),
        ("Open-end Spanners (Set)", "Open-end-Spanners-Set"),
        ("Test.allTheThings() T-Shirt (Red)", "Test.allTheThings-T-Shirt-Red"),
        ("Martillo de carpintería", "Martillo-de-carpinteria"),
    ],
)
def test_safe_filename_normaliza_nombres_reales(raw, expected):
    assert safe_filename(raw) == expected


@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd", "..\\..\\windows\\system32", "/absoluto/x", "....//....//x"],
)
def test_safe_filename_neutraliza_path_traversal(hostile):
    """El nombre viene de la pagina scrapeada: es entrada no confiable."""
    result = safe_filename(hostile)
    assert "/" not in result
    assert "\\" not in result
    assert not result.startswith(".")


def test_safe_filename_nunca_devuelve_vacio():
    assert safe_filename("///") == "producto"
    assert safe_filename("") == "producto"


def test_safe_filename_respeta_el_largo_maximo():
    assert len(safe_filename("a" * 500, max_length=60)) == 60
