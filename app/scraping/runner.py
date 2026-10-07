"""Registro de scrapers y punto de entrada unico para ejecutarlos."""

from collections.abc import Awaitable, Callable

from playwright.async_api import BrowserContext

from app.scraping.browser import browser_context
from app.scraping.sites import practice_software_testing, saucedemo
from app.scraping.types import ScrapedProduct

ScraperFn = Callable[[BrowserContext, str | None], Awaitable[list[ScrapedProduct]]]

SCRAPERS: dict[str, tuple[ScraperFn, str, str]] = {
    "saucedemo": (saucedemo.scrape, "Saucedemo", saucedemo.BASE_URL),
    "practicesoftware": (
        practice_software_testing.scrape,
        "Practice Software Testing",
        practice_software_testing.BASE_URL,
    ),
}


class UnsupportedTaskError(ValueError):
    """task_id sin scraper registrado."""


def get_scraper(task_id: str) -> ScraperFn:
    try:
        return SCRAPERS[task_id][0]
    except KeyError as exc:
        supported = ", ".join(sorted(SCRAPERS))
        raise UnsupportedTaskError(
            f"task_id '{task_id}' no soportado. Disponibles: {supported}"
        ) from exc


def supported_sites() -> list[tuple[str, str, str]]:
    """(code, name, base_url) de cada sitio soportado, para sembrar la base de datos."""
    return [(code, name, base_url) for code, (_, name, base_url) in SCRAPERS.items()]


async def run_scraper(task_id: str, lookup_key: str | None) -> list[ScrapedProduct]:
    scraper = get_scraper(task_id)
    async with browser_context() as context:
        return await scraper(context, lookup_key)
