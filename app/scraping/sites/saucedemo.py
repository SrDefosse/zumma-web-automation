from playwright.async_api import async_playwright
from typing import List, Dict

async def scrape_saucedemo(lookup_key: str | None) -> List[Dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        await page.goto("https://www.saucedemo.com/")
        await page.fill('[data-test="username"]', "standard_user")
        await page.fill('[data-test="password"]', "secret_sauce")
        await page.click('[data-test="login-button"]')

        await page.wait_for_selector('[data-test="inventory-item"]')

        # si lookup_key viene se filtra
        cards = await page.query_selector_all('[data-test="inventory-item"]')
        data = []
        for c in cards:
            name = (await (await c.query_selector('[data-test="inventory-item-name"]')).inner_text()).strip()
            if lookup_key and lookup_key.lower() not in name.lower():
                continue
            price = (await (await c.query_selector('[data-test="inventory-item-price"]')).inner_text()).strip()
            desc = (await (await c.query_selector('[data-test="inventory-item-desc"]')).inner_text()).strip()
            img_el = await c.query_selector('img[data-test*="inventory-item"][data-test*="img"]')
            img_url = await img_el.get_attribute("src")
            if img_url and img_url.startswith("/"):
                img_url = "https://www.saucedemo.com" + img_url
            data.append({"name": name, "price": price, "description": desc, "image_url": img_url})
        
        print(f"Total productos encontrados en SauceDemo: {len(data)}")
        await browser.close()
        return data
