from playwright.async_api import async_playwright, BrowserContext, Locator
from typing import List, Dict, Set, Optional
from urllib.parse import urljoin

BASE = "https://practicesoftwaretesting.com"

async def get_product_name(element: Locator) -> str:
    # Intenta obtener el nombre del producto usando múltiples selectores con Locator.
    name_selectors = [
        "[data-test='product-name']", 
        ".product-name", 
        ".card-title"
    ]
    
    for selector in name_selectors:
        try:
            name_locator = element.locator(selector)
            if await name_locator.count() > 0:
                name = (await name_locator.inner_text()).strip()
                if name:
                    return name
        except Exception:
            continue
    
    return ""

async def get_product_price(element: Locator) -> str:
    # intenta obtener el precio del producto usando varios selectores con Locator.
    price_selectors = [
        "[data-test='product-price']", 
        ".product-price"
    ]
    
    for selector in price_selectors:
        try:
            price_locator = element.locator(selector)
            if await price_locator.count() > 0:
                price = (await price_locator.inner_text()).strip()
                if price:
                    return price
        except Exception:
            continue
    
    return ""

async def get_product_image_url(element: Locator) -> str:
    # obtiene la url de la imagen del producto usando Locator.
    try:
        img_locator = element.locator("img")
        if await img_locator.count() > 0:
            raw_img = await img_locator.get_attribute("src")
            if raw_img:
                if raw_img.startswith("//"):
                    return "https:" + raw_img
                elif raw_img.startswith("/"):
                    return BASE + raw_img
                elif raw_img.startswith("http"):
                    return raw_img
                else:
                    return f"{BASE}/{raw_img}"
    except Exception:
        pass
    
    return "https://via.placeholder.com/150x150.png?text=No+Image"

async def scrape_product_detail(context: BrowserContext, url: str) -> Dict[str, str]:
    price = "N/A"
    desc = ""
    detail_page = None
    
    try:
        detail_page = await context.new_page()
        await detail_page.goto(url, wait_until="domcontentloaded", timeout=15000)
        
        # Intentar obtener el precio
        try:
            await detail_page.wait_for_selector("[data-test='unit-price']", timeout=5000)
            price_el = await detail_page.query_selector("[data-test='unit-price']")
            if price_el:
                price = (await price_el.inner_text()).strip()
        except Exception:
            print(f"Precio no encontrado en {url}")
        
        # Intentar obtener la descripción
        try:
            await detail_page.wait_for_selector("[data-test='product-description']", timeout=5000)
            desc_el = await detail_page.query_selector(
                "p#description[data-test='product-description'], [data-test='product-description'], p#description, p.product-description"
            )
            if desc_el:
                scraped_desc = (await desc_el.inner_text()).strip()
                if scraped_desc:
                    desc = scraped_desc
        except Exception:
            print(f"Descripción no encontrada en {url}")
            
    except Exception as e:
        print(f"Fallo al obtener detalles de {url}: {e}")
    finally:
        if detail_page:
            await detail_page.close()
    
    return {"price": price, "description": desc}

async def scrape_practice(lookup_key: str | None) -> List[Dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        data: List[Dict] = []
        seen_links: Set[str] = set()
        

        total_products_found = 0
        products_per_category = {}

        category_urls = [
            f"{BASE}",
            f"{BASE}/category/hand-tools",
            f"{BASE}/category/power-tools", 
            f"{BASE}/category/other",
            f"{BASE}/rentals",
        ]

        for category_url in category_urls:
            try:
                print(f"Iniciando scraping de categoria: {category_url}")
                products_per_category[category_url] = 0
                
                await page.goto(category_url, wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(1000)

                # para rentals 
                if "rentals" in category_url:
                    
                    # se seleccionan todos los contenedores de productos de alquiler
                    rental_product_containers = await page.query_selector_all("[data-test^='product-']")
                    print(f"Encontrados {len(rental_product_containers)} productos de alquiler en la página.")

                    rental_products = []
                    for container in rental_product_containers:
                        # se obtiene el id del producto desde data-test
                        data_test = await container.get_attribute("data-test")
                        product_id = data_test.split("product-")[-1]
                        product_url = f"{BASE}/product/{product_id}"

                        if product_url in seen_links:
                            continue
                        
                        # se obtiene nombre del producto
                        name = ""
                        name_el = await container.query_selector(".card-title")
                        if name_el:
                            name = (await name_el.inner_text()).strip()

                        if not name:
                            continue
                        
                        # se obtiene url de la imagen
                        img_url = ""
                        img_el = await container.query_selector("img")
                        if img_el:
                            raw_img = await img_el.get_attribute("src")
                            if raw_img:
                                img_url = urljoin(BASE, raw_img)

                        rental_products.append({
                            "name": name,
                            "product_url": product_url,
                            "image_url": img_url or "https://via.placeholder.com/150x150.png?text=No+Image",
                        })

                    print(f"{len(rental_products)} productos de alquiler encontrados.")

                    # visitar cada rental para obtener precio y descripción
                    for item in rental_products:
                        if item["product_url"] in seen_links:
                            continue
                        seen_links.add(item["product_url"])

                        # usar función auxiliar para obtener detalles
                        details = await scrape_product_detail(ctx, item["product_url"])
                        price = details["price"]
                        desc = details["description"]

                        data.append({
                            "name": item["name"],
                            "price": f"${price}" if price != "N/A" else "N/A",
                            "description": desc,
                            "image_url": item["image_url"],
                        })
                        
                        total_products_found += 1
                        products_per_category[category_url] += 1
                        
                        print(f"Producto RENTAL #{total_products_found} agregado: {item['name']} - Precio: {price} - Desc: {'SÍ' if desc else 'NO'}")
                else:
                    current_page = 1 

                    while True:
                        print(f"Scraping pagina {current_page} de {category_url}")
                        
                        # encontrar cards de productos en la página actual usando Locators
                        product_cards_locator = None
                        for sel in [".product-card", ".card"]:
                            cards_locator = page.locator(sel)
                            if await cards_locator.count() > 0:
                                product_cards_locator = cards_locator
                                break

                        if not product_cards_locator or await product_cards_locator.count() == 0:
                            print(f"No cards en {page.url}")
                            break

                        cards_count = await product_cards_locator.count()
                        print(f"Encontradas {cards_count} cards en pagina {current_page}")

                        # snapshot de productos de esta página
                        page_products = []
                        for i in range(cards_count):
                            card_locator = product_cards_locator.nth(i)
                            
                            # usar función auxiliar para obtener nombre
                            name = await get_product_name(card_locator)
                            if not name:
                                continue
                            if lookup_key and lookup_key.lower() not in name.lower():
                                continue

                            # usar función auxiliar para obtener precio
                            price = await get_product_price(card_locator)

                            # usar función auxiliar para obtener imagen
                            img_url = await get_product_image_url(card_locator)

                            # se obtiene url del producto
                            product_url = ""
                            href = await card_locator.get_attribute("href")
                            if href:
                                product_url = href if href.startswith("http") else urljoin(BASE, href)

                            if not product_url or product_url in seen_links:
                                continue

                            page_products.append({
                                "name": name,
                                "price": price or "N/A",
                                "image_url": img_url,
                                "product_url": product_url,
                            })

                        print(f"{len(page_products)} productos encontrados en pagina {current_page}")

                        # para cada producto se obtiene descripción
                        for item in page_products:
                            if item["product_url"] in seen_links:
                                continue
                            seen_links.add(item["product_url"])

                            # usar función auxiliar para obtener detalles (solo necesitamos descripción)
                            details = await scrape_product_detail(ctx, item["product_url"])
                            desc = details["description"]

                            data.append({
                                "name": item["name"],
                                "price": item["price"],
                                "description": desc,
                                "image_url": item["image_url"],
                            })
                            
                            total_products_found += 1
                            products_per_category[category_url] += 1
                            
                            print(f"Producto #{total_products_found} agregado: {item['name']} - Descripción: {'SÍ' if desc else 'NO'}")

                        # lógica de paginación
                        navigated = False
                        
                        try:
                            print(f"Buscando navegación desde pagina {current_page}")
                            
                            # se captura contenido actual para detectar cambios usando Locators
                            current_cards_locator = page.locator(".card")
                            current_product_count = await current_cards_locator.count()
                            
                            # se obtiene nombres de los primeros productos para comparar
                            current_names = []
                            for i in range(min(3, current_product_count)):
                                try:
                                    card_locator = current_cards_locator.nth(i)
                                    name_locator = card_locator.locator("[data-test='product-name']")
                                    if await name_locator.count() > 0:
                                        name = await name_locator.inner_text()
                                        current_names.append(name.strip())
                                except:
                                    pass
                            
                            print(f"Pagina actual: {current_product_count} productos - {current_names[:2]}")
                            
                            # verificar si existe el botón Next usando Locator
                            next_selector = 'a[aria-label="Next"][role="button"].page-link'
                            next_locator = page.locator(next_selector)
                            
                            if await next_locator.count() > 0:
                                # verificar si está visible y habilitado
                                is_visible = await next_locator.is_visible()
                                if is_visible:
                                    print(f"Botón Next encontrado y visible, haciendo click...")
                                    
                                    # hacer click directo
                                    await page.click(next_selector)
                                    
                                    # esperar a que el contenido se actualice
                                    await page.wait_for_timeout(2000) 
                                    
                                    # verificar si el contenido cambió usando Locators
                                    new_cards_locator = page.locator(".card")
                                    new_product_count = await new_cards_locator.count()
                                    new_names = []
                                    
                                    for i in range(min(3, new_product_count)):
                                        try:
                                            card_locator = new_cards_locator.nth(i)
                                            name_locator = card_locator.locator("[data-test='product-name']")
                                            if await name_locator.count() > 0:
                                                name = await name_locator.inner_text()
                                                new_names.append(name.strip())
                                        except:
                                            pass
                                    
                                    print(f"Nueva página: {new_product_count} productos - {new_names[:2]}")
                                    
                                    # verificar si realmente cambió el contenido
                                    if new_names != current_names and new_product_count > 0:
                                        current_page += 1
                                        navigated = True
                                        print(f"Navegación exitosa a página {current_page}")
                                    else:
                                        print(f"Contenido no cambió, posiblemente última página")
                                else:
                                    print(f"Botón Next existe pero no está visible")
                            else:
                                print(f"Botón Next no encontrado")
                            
                            # si no funcionó con Next, intentar con número de página específico
                            if not navigated:
                                next_page_num = current_page + 1
                                page_num_selector = f'a[aria-label="Page-{next_page_num}"][role="button"].page-link'
                                page_num_locator = page.locator(page_num_selector)
                                
                                if await page_num_locator.count() > 0:
                                    is_visible = await page_num_locator.is_visible()
                                    if is_visible:
                                        print(f"Intentando con botón página {next_page_num}")
                                        
                                        await page.click(page_num_selector)
                                        await page.wait_for_timeout(2000)
                                        
                                        # verificar cambio de contenido usando Locators
                                        new_cards_locator = page.locator(".card")
                                        new_product_count = await new_cards_locator.count()
                                        new_names = []
                                        
                                        for i in range(min(3, new_product_count)):
                                            try:
                                                card_locator = new_cards_locator.nth(i)
                                                name_locator = card_locator.locator("[data-test='product-name']")
                                                if await name_locator.count() > 0:
                                                    name = await name_locator.inner_text()
                                                    new_names.append(name.strip())
                                            except:
                                                pass
                                        
                                        if new_names != current_names and new_product_count > 0:
                                            current_page = next_page_num
                                            navigated = True
                                            print(f"Navegación exitosa a página {current_page}")
                                        else:
                                            print(f"No hay cambio de contenido en página {next_page_num}")
                                    else:
                                        print(f"Botón página {next_page_num} existe pero no está visible")
                                else:
                                    print(f"No existe botón para página {next_page_num}")
                            
                            if not navigated:
                                print(f"No hay más páginas disponibles en {category_url}")
                                break
                                
                        except Exception as e:
                            print(f"Error en paginación: {e}")
                            break

                print(f"Categoría {category_url} completada: {products_per_category[category_url]} productos")

            except Exception as e:
                print(f"Error en categoría {category_url}: {e}")
                continue

        await browser.close()
        
        # resumen final
        print(f"\nRESUMEN FINAL:")
        print(f"Total productos únicos de Practice: {len(data)}")
        
        return data