"""Gestion del navegador de Playwright.

Un solo lugar decide headless, timeouts y cuantos navegadores pueden existir a la vez.
El semaforo es necesario: sin tope, N jobs concurrentes significan N chromium
compitiendo por la memoria del contenedor.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from playwright.async_api import BrowserContext, async_playwright

from app.config import settings
from app.logging_config import get_logger

log = get_logger(__name__)

_browser_semaphore = asyncio.Semaphore(settings.scraper_max_concurrency)

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@asynccontextmanager
async def browser_context() -> AsyncIterator[BrowserContext]:
    """Entrega un BrowserContext listo para usar y garantiza su cierre."""
    async with _browser_semaphore:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=settings.playwright_headless,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            try:
                context = await browser.new_context(
                    user_agent=_USER_AGENT,
                    viewport={"width": 1440, "height": 900},
                )
                context.set_default_timeout(settings.playwright_timeout_ms)
                context.set_default_navigation_timeout(settings.playwright_timeout_ms)
                try:
                    yield context
                finally:
                    await context.close()
            finally:
                await browser.close()
