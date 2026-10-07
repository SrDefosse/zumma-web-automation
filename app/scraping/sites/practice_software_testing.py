"""Scraper de https://practicesoftwaretesting.com/ (catalogo publico, sin login).

El listado no trae la descripcion, asi que hace dos pasadas: primero recorre los
listados paginados, despues visita el detalle de cada producto unico.
"""

import asyncio
from typing import Any

from playwright.async_api import BrowserContext

from app.config import settings
from app.logging_config import get_logger
from app.scraping.types import ScrapedProduct
from app.scraping.urls import absolutize

log = get_logger(__name__)

BASE_URL = "https://practicesoftwaretesting.com"

LISTING_PATHS = (
    "/",
    "/category/hand-tools",
    "/category/power-tools",
    "/category/other",
    "/rentals",
)

MAX_PAGES_PER_LISTING = 25
DETAIL_CONCURRENCY = 4

_EXTRACT_CARDS_JS = """
() => {
  const marked = Array.from(document.querySelectorAll('[data-test^="product-"]'));
  const cards = marked.length
    ? marked
    : Array.from(document.querySelectorAll('a.card, .product-card'));
  return cards.map((card) => {
    const pick = (selectors) => {
      for (const selector of selectors) {
        const node = card.querySelector(selector);
        const text = node && node.innerText ? node.innerText.trim() : '';
        if (text) return text;
      }
      return '';
    };
    const anchor = card.matches('a[href]') ? card : card.querySelector('a[href]');
    const marker = card.getAttribute('data-test') || '';
    const img = card.querySelector('img');
    return {
      product_id: marker.indexOf('product-') === 0 ? marker.substring(8) : '',
      name: pick(['[data-test="product-name"]', '.product-name', '.card-title']),
      price: pick(['[data-test="product-price"]', '.product-price']),
      image_url: img ? img.getAttribute('src') || '' : '',
      href: anchor ? anchor.getAttribute('href') || '' : '',
    };
  });
}
"""

_EXTRACT_DETAIL_JS = """
() => {
  const pick = (selectors) => {
    for (const selector of selectors) {
      const node = document.querySelector(selector);
      const text = node && node.innerText ? node.innerText.trim() : '';
      if (text) return text;
    }
    return '';
  };
  return {
    price: pick(['[data-test="unit-price"]', '[data-test="product-price"]']),
    description: pick([
      'p#description[data-test="product-description"]',
      '[data-test="product-description"]',
      'p#description',
      'p.product-description',
    ]),
  };
}
"""


def listing_url(path: str, page_number: int) -> str:
    """URL de un listado para una pagina dada.

    El sitio pagina por query param, asi que la navegacion es determinista y no hace
    falta clickear "Next" ni detectar el cambio de pagina por el contenido.
    """
    base = f"{BASE_URL}{path}" if path.startswith("/") else f"{BASE_URL}/{path}"
    if page_number <= 1:
        return base
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}page={page_number}"


def card_key(card: dict[str, Any]) -> str:
    """Identidad estable de una card, para deduplicar entre categorias y paginas."""
    product_id = (card.get("product_id") or "").strip()
    if product_id:
        return f"id:{product_id}"
    href = (card.get("href") or "").strip()
    if href:
        return f"url:{absolutize(BASE_URL, href)}"
    return f"name:{(card.get('name') or '').strip().lower()}"


def detail_url(card: dict[str, Any]) -> str | None:
    """URL de la pagina de detalle de una card, o None si no se puede determinar."""
    href = (card.get("href") or "").strip()
    if href:
        return absolutize(BASE_URL, href)
    product_id = (card.get("product_id") or "").strip()
    return f"{BASE_URL}/product/{product_id}" if product_id else None


def matches_lookup(name: str, lookup_key: str | None) -> bool:
    if not lookup_key:
        return True
    return lookup_key.lower().strip() in name.lower()


def select_new_cards(
    raw_cards: list[dict[str, Any]], lookup_key: str | None, seen: set[str]
) -> tuple[list[dict[str, Any]], int]:
    """Filtra las cards ya vistas y las que no matchean el lookup_key.

    Devuelve (cards a scrapear, cantidad de cards nuevas). La segunda cuenta incluye las
    descartadas por lookup_key: es la senial de "esta pagina aporto algo" que corta la
    paginacion, y debe ser independiente del filtro.
    """
    new_cards = [card for card in raw_cards if card_key(card) not in seen]
    for card in new_cards:
        seen.add(card_key(card))

    selected = [
        card
        for card in new_cards
        if (card.get("name") or "").strip() and matches_lookup(card["name"], lookup_key)
    ]
    return selected, len(new_cards)


async def _collect_listing_cards(
    context: BrowserContext, path: str, lookup_key: str | None, seen: set[str]
) -> list[dict[str, Any]]:
    """Recorre un listado pagina por pagina y devuelve sus cards nuevas."""
    page = await context.new_page()
    collected: list[dict[str, Any]] = []
    try:
        for page_number in range(1, MAX_PAGES_PER_LISTING + 1):
            url = listing_url(path, page_number)
            try:
                await page.goto(url, wait_until="networkidle")
            except Exception as exc:  # noqa: BLE001 - un listado caido no debe matar el job
                log.warning("no se pudo abrir el listado", url=url, error=str(exc))
                break

            raw_cards = await page.evaluate(_EXTRACT_CARDS_JS)
            if not raw_cards:
                break

            selected, new_count = select_new_cards(raw_cards, lookup_key, seen)
            collected.extend(selected)

            log.debug(
                "pagina de listado procesada",
                url=url,
                cards=len(raw_cards),
                nuevas=new_count,
                seleccionadas=len(selected),
            )

            if new_count == 0:
                break
    finally:
        await page.close()

    return collected


async def _fetch_detail(
    context: BrowserContext, url: str | None, semaphore: asyncio.Semaphore
) -> dict[str, str]:
    """Lee precio y descripcion de la pagina de detalle. Nunca lanza."""
    empty = {"price": "", "description": ""}
    if not url:
        return empty

    async with semaphore:
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            try:
                await page.wait_for_selector(
                    '[data-test="product-description"], p#description',
                    timeout=settings.playwright_timeout_ms // 3,
                )
            except Exception:  # noqa: BLE001 - la descripcion es opcional
                log.debug("descripcion no encontrada", url=url)
            return await page.evaluate(_EXTRACT_DETAIL_JS)
        except Exception as exc:  # noqa: BLE001 - un detalle caido no debe matar el job
            log.warning("no se pudo leer el detalle del producto", url=url, error=str(exc))
            return empty
        finally:
            await page.close()


async def scrape(context: BrowserContext, lookup_key: str | None = None) -> list[ScrapedProduct]:
    seen: set[str] = set()
    cards: list[dict[str, Any]] = []

    for path in LISTING_PATHS:
        cards.extend(await _collect_listing_cards(context, path, lookup_key, seen))

    semaphore = asyncio.Semaphore(DETAIL_CONCURRENCY)
    detail_urls = [detail_url(card) for card in cards]
    details = await asyncio.gather(*(_fetch_detail(context, url, semaphore) for url in detail_urls))

    products = [
        ScrapedProduct.build(
            name=card["name"],
            price=card.get("price") or detail.get("price"),
            description=detail.get("description"),
            image_url=absolutize(BASE_URL, card.get("image_url")),
            source_url=url,
        )
        for card, detail, url in zip(cards, details, detail_urls, strict=True)
    ]

    log.info(
        "scraping de practicesoftwaretesting finalizado",
        cards=len(cards),
        productos=len(products),
        lookup_key=lookup_key,
    )
    return products
