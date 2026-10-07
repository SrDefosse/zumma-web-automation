"""Scraper de https://www.saucedemo.com/ (requiere login)."""

from typing import Any

from playwright.async_api import Page

from app.config import settings
from app.logging_config import get_logger
from app.scraping.types import ScrapedProduct
from app.scraping.urls import absolutize

log = get_logger(__name__)

BASE_URL = "https://www.saucedemo.com"

_EXTRACT_CARDS_JS = """
() => Array.from(document.querySelectorAll('[data-test="inventory-item"]')).map((card) => {
  const pick = (selector) => card.querySelector(selector)?.innerText ?? '';
  return {
    name: pick('[data-test="inventory-item-name"]'),
    price: pick('[data-test="inventory-item-price"]'),
    description: pick('[data-test="inventory-item-desc"]'),
    image_url: card.querySelector('img')?.getAttribute('src') ?? '',
    source_url: card.querySelector('a[href]')?.getAttribute('href') ?? '',
  };
})
"""


def parse_cards(
    raw_cards: list[dict[str, Any]], lookup_key: str | None = None
) -> list[ScrapedProduct]:
    """Convierte las cards crudas en productos normalizados. Funcion pura."""
    needle = lookup_key.lower().strip() if lookup_key else None
    products: list[ScrapedProduct] = []

    for card in raw_cards:
        name = (card.get("name") or "").strip()
        if not name:
            continue
        if needle and needle not in name.lower():
            continue
        products.append(
            ScrapedProduct.build(
                name=name,
                price=card.get("price"),
                description=card.get("description"),
                image_url=absolutize(BASE_URL, card.get("image_url")),
                source_url=absolutize(BASE_URL, card.get("source_url")) or None,
            )
        )
    return products


async def _login(page: Page) -> None:
    await page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
    await page.fill('[data-test="username"]', settings.saucedemo_username)
    await page.fill('[data-test="password"]', settings.saucedemo_password)
    await page.click('[data-test="login-button"]')

    error = page.locator('[data-test="error"]')
    try:
        await page.wait_for_selector(
            '[data-test="inventory-list"], [data-test="error"]', state="attached"
        )
    except Exception as exc:  # noqa: BLE001 - se reporta como fallo del job
        raise RuntimeError(f"saucedemo no cargo el inventario tras el login: {exc}") from exc

    if await error.count() > 0:
        raise RuntimeError(f"Login rechazado por saucedemo: {(await error.inner_text()).strip()}")


async def scrape(context, lookup_key: str | None = None) -> list[ScrapedProduct]:
    page = await context.new_page()
    try:
        await _login(page)
        await page.wait_for_selector('[data-test="inventory-item"]')
        raw_cards = await page.evaluate(_EXTRACT_CARDS_JS)
        products = parse_cards(raw_cards, lookup_key)
        log.info(
            "scraping de saucedemo finalizado",
            cards_encontradas=len(raw_cards),
            productos=len(products),
            lookup_key=lookup_key,
        )
        return products
    finally:
        await page.close()
