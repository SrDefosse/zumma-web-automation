"""Tests de la extraccion de productos sin levantar un navegador.

Los scrapers devuelven las cards crudas desde una unica evaluacion en el browser y el
parseo ocurre en Python. Eso permite testear la logica de extraccion con fixtures.
"""

from decimal import Decimal

import pytest

from app.scraping.sites import practice_software_testing as practice
from app.scraping.sites import saucedemo
from app.scraping.urls import absolutize

SAUCEDEMO_CARDS = [
    {
        "name": "Sauce Labs Backpack",
        "price": "$29.99",
        "description": "carry.allTheThings() with the sleek, streamlined Sly Pack",
        "image_url": "/static/media/sauce-backpack.jpg",
        "source_url": "/inventory-item.html?id=4",
    },
    {
        "name": "Sauce Labs Bike Light",
        "price": "$9.99",
        "description": "A red light isn't the desired state in testing",
        "image_url": "https://www.saucedemo.com/static/media/bike-light.jpg",
        "source_url": "/inventory-item.html?id=0",
    },
    {"name": "", "price": "$1.00", "description": "", "image_url": "", "source_url": ""},
]


def test_saucedemo_parse_cards_normaliza_y_descarta_vacias():
    products = saucedemo.parse_cards(SAUCEDEMO_CARDS)

    assert len(products) == 2
    backpack = products[0]
    assert backpack.name == "Sauce Labs Backpack"
    assert backpack.price_text == "$29.99"
    assert backpack.price_amount == Decimal("29.99")
    assert backpack.price_currency == "USD"
    assert backpack.image_url == "https://www.saucedemo.com/static/media/sauce-backpack.jpg"
    assert backpack.source_url == "https://www.saucedemo.com/inventory-item.html?id=4"


def test_saucedemo_parse_cards_no_rompe_urls_absolutas():
    products = saucedemo.parse_cards(SAUCEDEMO_CARDS)
    assert products[1].image_url == "https://www.saucedemo.com/static/media/bike-light.jpg"


@pytest.mark.parametrize(
    ("lookup_key", "expected"),
    [
        (None, 2),
        ("backpack", 1),
        ("BACKPACK", 1),
        ("  bike  ", 1),
        ("sauce labs", 2),
        ("inexistente", 0),
    ],
)
def test_saucedemo_lookup_key_filtra_por_nombre(lookup_key, expected):
    assert len(saucedemo.parse_cards(SAUCEDEMO_CARDS, lookup_key)) == expected


@pytest.mark.parametrize(
    ("path", "page_number", "expected"),
    [
        ("/", 1, "https://practicesoftwaretesting.com/"),
        ("/", 2, "https://practicesoftwaretesting.com/?page=2"),
        ("/category/hand-tools", 1, "https://practicesoftwaretesting.com/category/hand-tools"),
        (
            "/category/hand-tools",
            3,
            "https://practicesoftwaretesting.com/category/hand-tools?page=3",
        ),
        ("/rentals", 2, "https://practicesoftwaretesting.com/rentals?page=2"),
    ],
)
def test_practice_listing_url_pagina_por_query_param(path, page_number, expected):
    """La paginacion es determinista; no depende de clickear "Next" ni de comparar nombres."""
    assert practice.listing_url(path, page_number) == expected


def test_practice_card_key_prefiere_el_id_del_producto():
    card = {"product_id": "01J7", "href": "/product/01J7", "name": "Claw Hammer"}
    assert practice.card_key(card) == "id:01J7"


def test_practice_card_key_cae_al_href_y_luego_al_nombre():
    assert practice.card_key({"href": "/product/abc"}) == (
        "url:https://practicesoftwaretesting.com/product/abc"
    )
    assert practice.card_key({"name": "Claw Hammer"}) == "name:claw hammer"


def test_practice_detail_url_reconstruye_desde_el_product_id():
    assert practice.detail_url({"product_id": "01J7"}) == (
        "https://practicesoftwaretesting.com/product/01J7"
    )
    assert practice.detail_url({}) is None


def test_practice_select_new_cards_deduplica_entre_paginas():
    """Un producto que aparece en dos categorias se scrapea una sola vez."""
    seen: set[str] = set()
    pagina_1 = [{"product_id": "1", "name": "Claw Hammer"}, {"product_id": "2", "name": "Pliers"}]

    selected, new_count = practice.select_new_cards(pagina_1, None, seen)
    assert [card["name"] for card in selected] == ["Claw Hammer", "Pliers"]
    assert new_count == 2

    selected, new_count = practice.select_new_cards(pagina_1, None, seen)
    assert selected == []
    assert new_count == 0


def test_practice_select_new_cards_cuenta_novedad_aparte_del_filtro():
    """new_count no debe depender del lookup_key.

    Si contara solo las cards que matchean, una pagina llena de productos nuevos que no
    matchean cortaria la paginacion y nunca se llegaria a los que si matchean.
    """
    seen: set[str] = set()
    cards = [{"product_id": "1", "name": "Pliers"}, {"product_id": "2", "name": "Wood Saw"}]

    selected, new_count = practice.select_new_cards(cards, "hammer", seen)
    assert selected == []
    assert new_count == 2


def test_practice_select_new_cards_descarta_cards_sin_nombre():
    seen: set[str] = set()
    selected, new_count = practice.select_new_cards(
        [{"product_id": "1", "name": "  "}, {"product_id": "2", "name": "Pliers"}], None, seen
    )
    assert [card["name"] for card in selected] == ["Pliers"]
    assert new_count == 2


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/img/x.jpg", "https://example.com/img/x.jpg"),
        ("img/x.jpg", "https://example.com/img/x.jpg"),
        ("//cdn.example.com/x.jpg", "https://cdn.example.com/x.jpg"),
        ("https://otro.com/x.jpg", "https://otro.com/x.jpg"),
        ("http://otro.com/x.jpg", "http://otro.com/x.jpg"),
        ("", ""),
        (None, ""),
    ],
)
def test_absolutize_cubre_las_formas_de_url_de_los_sitios(raw, expected):
    assert absolutize("https://example.com", raw) == expected
