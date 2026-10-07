"""Tests del ciclo de vida de un job: ejecucion, fallo y recuperacion.

El scraper y la descarga de imagenes se reemplazan por dobles, asi que estos tests
cubren la maquina de estados sin navegador ni red.
"""

from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Job, JobStatus, Product, ProductImage, Site
from app.scraping.types import ScrapedProduct
from app.services import tasks as tasks_service
from app.services.images import ImageDownloadError, StoredImage


@pytest.fixture
async def session_factory(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            Site(id=1, code="saucedemo", name="Saucedemo", base_url="https://www.saucedemo.com")
        )
        await session.commit()

    monkeypatch.setattr(tasks_service, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


def _producto(name: str = "Sauce Labs Backpack") -> ScrapedProduct:
    return ScrapedProduct(
        name=name,
        price_text="$29.99",
        price_amount=Decimal("29.99"),
        price_currency="USD",
        description="carry.allTheThings()",
        image_url="https://www.saucedemo.com/a.jpg",
        source_url="https://www.saucedemo.com/inventory-item.html?id=4",
    )


@pytest.fixture
def imagen_ok(monkeypatch: pytest.MonkeyPatch):
    async def fake_download(url, product_name, client=None):
        return StoredImage(
            filename=f"{product_name.replace(' ', '-')}.jpg",
            file_path=f"storage/images/{product_name.replace(' ', '-')}.jpg",
            content_type="image/jpeg",
            size_bytes=1024,
        )

    monkeypatch.setattr(tasks_service, "download_image", fake_download)


async def _crear_job(factory, status: JobStatus = JobStatus.pending, lookup_key=None):
    job_id = uuid4()
    async with factory() as session:
        session.add(Job(id=job_id, site_id=1, status=status, lookup_key=lookup_key))
        await session.commit()
    return job_id


async def test_run_job_completa_y_persiste_los_precios_normalizados(
    session_factory, monkeypatch, imagen_ok
):
    job_id = await _crear_job(session_factory)

    async def fake_scraper(task_id, lookup_key):
        assert task_id == "saucedemo"
        return [_producto()]

    monkeypatch.setattr(tasks_service, "run_scraper", fake_scraper)
    await tasks_service.run_job(job_id)

    async with session_factory() as session:
        job = await session.get(Job, job_id)
        assert job.status is JobStatus.completed
        assert job.started_at is not None and job.finished_at is not None

        product = (await session.scalars(select(Product))).one()
        assert product.price_text == "$29.99"
        assert product.price_amount == Decimal("29.99")
        assert product.price_currency == "USD"

        image = (await session.scalars(select(ProductImage))).one()
        assert image.product_id == product.id


async def test_run_job_pasa_el_lookup_key_al_scraper(session_factory, monkeypatch, imagen_ok):
    job_id = await _crear_job(session_factory, lookup_key="backpack")
    recibido = {}

    async def fake_scraper(task_id, lookup_key):
        recibido["lookup_key"] = lookup_key
        return [_producto()]

    monkeypatch.setattr(tasks_service, "run_scraper", fake_scraper)
    await tasks_service.run_job(job_id)

    assert recibido["lookup_key"] == "backpack"


async def test_run_job_marca_failed_con_el_mensaje_de_error(session_factory, monkeypatch):
    job_id = await _crear_job(session_factory)

    async def scraper_roto(task_id, lookup_key):
        raise TimeoutError("el sitio no respondio")

    monkeypatch.setattr(tasks_service, "run_scraper", scraper_roto)
    await tasks_service.run_job(job_id)

    async with session_factory() as session:
        job = await session.get(Job, job_id)
        assert job.status is JobStatus.failed
        assert "el sitio no respondio" in job.error_message
        assert job.finished_at is not None


async def test_run_job_falla_si_el_scraper_no_devuelve_nada(session_factory, monkeypatch):
    """Un job que no extrae nada es un fallo, no un exito con lista vacia."""
    job_id = await _crear_job(session_factory, lookup_key="inexistente")

    async def scraper_vacio(task_id, lookup_key):
        return []

    monkeypatch.setattr(tasks_service, "run_scraper", scraper_vacio)
    await tasks_service.run_job(job_id)

    async with session_factory() as session:
        job = await session.get(Job, job_id)
        assert job.status is JobStatus.failed
        assert "inexistente" in job.error_message


async def test_run_job_guarda_el_producto_aunque_falle_su_imagen(session_factory, monkeypatch):
    job_id = await _crear_job(session_factory)

    async def fake_scraper(task_id, lookup_key):
        return [_producto()]

    async def download_roto(url, product_name, client=None):
        raise ImageDownloadError("404")

    monkeypatch.setattr(tasks_service, "run_scraper", fake_scraper)
    monkeypatch.setattr(tasks_service, "download_image", download_roto)
    await tasks_service.run_job(job_id)

    async with session_factory() as session:
        assert (await session.get(Job, job_id)).status is JobStatus.completed
        assert (await session.scalars(select(Product))).one().name == "Sauce Labs Backpack"
        assert (await session.scalars(select(ProductImage))).all() == []


async def test_run_job_deduplica_productos_con_el_mismo_nombre(
    session_factory, monkeypatch, imagen_ok
):
    """La constraint uq_products_job_name no debe hacer fallar el job entero."""
    job_id = await _crear_job(session_factory)

    async def fake_scraper(task_id, lookup_key):
        return [_producto(), _producto(), _producto("Otro")]

    monkeypatch.setattr(tasks_service, "run_scraper", fake_scraper)
    await tasks_service.run_job(job_id)

    async with session_factory() as session:
        assert (await session.get(Job, job_id)).status is JobStatus.completed
        nombres = (await session.scalars(select(Product.name).order_by(Product.id))).all()
        assert list(nombres) == ["Sauce Labs Backpack", "Otro"]


async def test_run_job_borra_las_imagenes_si_falla_el_commit(session_factory, monkeypatch):
    """Sin esta limpieza, un fallo al persistir deja archivos huerfanos en disco."""
    job_id = await _crear_job(session_factory)
    borrados: list[str] = []

    async def fake_scraper(task_id, lookup_key):
        return [_producto()]

    async def fake_download(url, product_name, client=None):
        return StoredImage(
            filename="a.jpg",
            file_path="storage/images/a.jpg",
            content_type="image/jpeg",
            size_bytes=1,
        )

    original_persist = tasks_service._persist_products

    async def persist_que_falla(session, job, products):
        async def commit_roto():
            raise RuntimeError("se cayo la base")

        monkeypatch.setattr(session, "commit", commit_roto)
        return await original_persist(session, job, products)

    monkeypatch.setattr(tasks_service, "run_scraper", fake_scraper)
    monkeypatch.setattr(tasks_service, "download_image", fake_download)
    monkeypatch.setattr(tasks_service, "delete_image", borrados.append)
    monkeypatch.setattr(tasks_service, "_persist_products", persist_que_falla)
    await tasks_service.run_job(job_id)

    assert borrados == ["storage/images/a.jpg"]
    async with session_factory() as session:
        assert (await session.get(Job, job_id)).status is JobStatus.failed


async def test_run_job_ignora_un_job_ya_terminado(session_factory, monkeypatch):
    """Un reintento de la cola no debe reejecutar un job que ya finalizo."""
    job_id = await _crear_job(session_factory, status=JobStatus.completed)
    llamadas = []

    async def fake_scraper(task_id, lookup_key):
        llamadas.append(task_id)
        return [_producto()]

    monkeypatch.setattr(tasks_service, "run_scraper", fake_scraper)
    await tasks_service.run_job(job_id)

    assert llamadas == []


async def test_run_job_con_job_inexistente_no_lanza(session_factory, monkeypatch):
    async def fake_scraper(task_id, lookup_key):
        raise AssertionError("no deberia llegar al scraper")

    monkeypatch.setattr(tasks_service, "run_scraper", fake_scraper)
    await tasks_service.run_job(uuid4())


async def test_recover_stale_jobs_rescata_los_in_progress(session_factory):
    colgado = await _crear_job(session_factory, status=JobStatus.in_progress)
    encolado = await _crear_job(session_factory, status=JobStatus.pending)
    terminado = await _crear_job(session_factory, status=JobStatus.completed)

    assert await tasks_service.recover_stale_jobs() == 1

    async with session_factory() as session:
        assert (await session.get(Job, colgado)).status is JobStatus.failed
        assert (await session.get(Job, encolado)).status is JobStatus.pending
        assert (await session.get(Job, terminado)).status is JobStatus.completed


async def test_seed_sites_es_idempotente(session_factory):
    async with session_factory() as session:
        await tasks_service.seed_sites(session)
        await tasks_service.seed_sites(session)
        codigos = sorted((await session.scalars(select(Site.code))).all())

    assert codigos == ["practicesoftware", "saucedemo"]
