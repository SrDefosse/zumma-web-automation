from playwright.async_api import async_playwright
from typing import List, Dict

async def scrape_saucedemo(lookup_key: str | None) -> List[Dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        await page.goto("https://www.saucedemo.com/")
        await page.fill("#user-name", "standard_user")
        await page.fill("#password", "secret_sauce")
        await page.click("#login-button")

        await page.wait_for_selector(".inventory_list")

        # si lookup_key viene se filtra
        cards = await page.query_selector_all(".inventory_item")
        data = []
        for c in cards:
            name = (await (await c.query_selector(".inventory_item_name")).inner_text()).strip()
            if lookup_key and lookup_key.lower() not in name.lower():
                continue
            price = (await (await c.query_selector(".inventory_item_price")).inner_text()).strip()
            desc = (await (await c.query_selector(".inventory_item_desc")).inner_text()).strip()
            img_el = await c.query_selector("img.inventory_item_img")
            img_url = await img_el.get_attribute("src")
            if img_url and img_url.startswith("/"):
                img_url = "https://www.saucedemo.com" + img_url
            data.append({"name": name, "price": price, "description": desc, "image_url": img_url})
        await browser.close()
        return data
