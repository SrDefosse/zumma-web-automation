import httpx, os, hashlib
from pathlib import Path

IMAGES_DIR = Path("storage/images")
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

async def download_image(url: str, hint_name: str) -> tuple[str, str]:
    # genera nombre con hash
    h = hashlib.sha1(f"{hint_name}-{url}".encode()).hexdigest()[:16]
    filename = f"{hint_name[:40]}-{h}.jpg".replace(" ", "-")
    file_path = IMAGES_DIR / filename

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        file_path.write_bytes(r.content)

    served_url = f"/images/{filename}"
    return str(file_path), served_url
