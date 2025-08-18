from app.scraping.sites.saucedemo import scrape_saucedemo
from app.scraping.sites.practice_software_testing import scrape_practice
from typing import List, Dict

async def run_scraper(task_id: str, lookup_key: str | None) -> List[Dict]:
    if task_id == "saucedemo":
        return await scrape_saucedemo(lookup_key)
    if task_id == "practicesoftware":
        return await scrape_practice(lookup_key)
    raise ValueError("Unsupported task_id")
