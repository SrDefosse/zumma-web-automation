"""Ciclo de vida de los jobs de scraping: creacion, ejecucion y lectura de resultados."""

from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import AsyncSessionLocal
from app.logging_config import get_logger
from app.models import Job, JobStatus, Product, ProductImage, Site
from app.schemas import ProductOut, TaskStatusOut
from app.scraping.runner import UnsupportedTaskError, get_scraper, run_scraper, supported_sites
from app.services.images import ImageDownloadError, delete_image, download_image

log = get_logger(__name__)


async def seed_sites(session: AsyncSession) -> None:
    """Asegura una fila en `sites` por cada scraper registrado. Idempotente."""
    existing = {code for code in (await session.scalars(select(Site.code))).all()}
    for code, name, base_url in supported_sites():
        if code not in existing:
            session.add(Site(code=code, name=name, base_url=base_url))
    await session.commit()


async def create_job(session: AsyncSession, task_id: str, lookup_key: str | None) -> UUID:
    """Crea un job en estado pending y devuelve su id.

    Resuelve el scraper antes de escribir para fallar rapido si el task_id no existe.
    """
    get_scraper(task_id)

    site_id = await session.scalar(select(Site.id).where(Site.code == task_id))
    if site_id is None:
        raise UnsupportedTaskError(f"El sitio '{task_id}' no esta registrado en la base de datos")

    job = Job(site_id=site_id, lookup_key=lookup_key, status=JobStatus.pending)
    session.add(job)
    await session.commit()
    log.info("job creado", job_id=str(job.id), task_id=task_id, lookup_key=lookup_key)
    return job.id


async def _claim_job(session: AsyncSession, job_id: UUID) -> tuple[Job, str] | None:
    """Marca el job como in_progress y devuelve (job, task_id).

    Carga el sitio en la misma consulta para resolver el task_id sin viajes extra
    a la base.
    """
    job = await session.scalar(
        select(Job).options(selectinload(Job.site)).where(Job.id == job_id).with_for_update()
    )
    if job is None:
        log.warning("job inexistente", job_id=str(job_id))
        return None
    if job.status.is_terminal:
        log.info("job ya finalizado, se ignora", job_id=str(job_id), status=job.status.value)
        return None

    task_id = job.site.code
    job.status = JobStatus.in_progress
    job.started_at = datetime.now(UTC)
    await session.commit()
    return job, task_id


async def _persist_products(session: AsyncSession, job: Job, products: list) -> int:
    """Descarga imagenes y persiste productos. Limpia los archivos si el commit falla."""
    downloaded: list[str] = []
    seen_names: set[str] = set()

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        try:
            for scraped in products:
                if scraped.name in seen_names:
                    log.debug("producto duplicado omitido", name=scraped.name)
                    continue
                seen_names.add(scraped.name)

                product = Product(
                    site_id=job.site_id,
                    job_id=job.id,
                    name=scraped.name,
                    description=scraped.description,
                    source_url=scraped.source_url,
                    price_text=scraped.price_text,
                    price_amount=scraped.price_amount,
                    price_currency=scraped.price_currency,
                )
                session.add(product)
                await session.flush()

                try:
                    stored = await download_image(scraped.image_url, scraped.name, client=client)
                except ImageDownloadError as exc:
                    log.warning(
                        "no se pudo descargar la imagen",
                        name=scraped.name,
                        url=scraped.image_url,
                        error=str(exc),
                    )
                    continue

                downloaded.append(stored.file_path)
                session.add(
                    ProductImage(
                        product_id=product.id,
                        filename=stored.filename,
                        file_path=stored.file_path,
                        source_url=scraped.image_url,
                        content_type=stored.content_type,
                        size_bytes=stored.size_bytes,
                    )
                )

            await session.commit()
        except Exception:
            await session.rollback()
            for file_path in downloaded:
                delete_image(file_path)
            raise

    return len(seen_names)


async def run_job(job_id: UUID) -> None:
    """Ejecuta un job de principio a fin. No propaga excepciones: las registra en el job."""
    async with AsyncSessionLocal() as session:
        claimed = await _claim_job(session, job_id)
        if claimed is None:
            return
        job, task_id = claimed

    log.info("job iniciado", job_id=str(job_id), task_id=task_id)
    try:
        products = await run_scraper(task_id=task_id, lookup_key=job.lookup_key)
        if not products:
            raise RuntimeError(
                "El scraping no devolvio productos"
                + (f" para lookup_key='{job.lookup_key}'" if job.lookup_key else "")
            )

        async with AsyncSessionLocal() as session:
            fresh_job = await session.get(Job, job_id)
            stored_count = await _persist_products(session, fresh_job, products)
            fresh_job.status = JobStatus.completed
            fresh_job.finished_at = datetime.now(UTC)
            await session.commit()

        log.info("job completado", job_id=str(job_id), productos=stored_count)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo se refleja en el estado del job
        log.exception("job fallido", job_id=str(job_id), task_id=task_id)
        await _mark_failed(job_id, f"{type(exc).__name__}: {exc}")


async def _mark_failed(job_id: UUID, error_message: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                status=JobStatus.failed,
                error_message=error_message[:2000],
                finished_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def recover_stale_jobs() -> int:
    """Marca como failed los jobs que quedaron in_progress tras una caida del worker.

    Sin esto un reinicio deja jobs colgados en in_progress para siempre y el cliente
    poll-ea indefinidamente. Los jobs en `pending` no se tocan: siguen encolados en
    Redis y el worker los va a tomar.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Job)
            .where(Job.status == JobStatus.in_progress)
            .values(
                status=JobStatus.failed,
                error_message="El worker se reinicio antes de terminar este job",
                finished_at=datetime.now(UTC),
            )
        )
        await session.commit()
        recovered = result.rowcount or 0

    if recovered:
        log.warning("jobs interrumpidos marcados como failed", cantidad=recovered)
    return recovered


async def get_job_result(session: AsyncSession, job_id: UUID) -> TaskStatusOut | None:
    """Devuelve el estado del job y, si esta completado, sus productos."""
    job = await session.get(Job, job_id)
    if job is None:
        return None

    if job.status is JobStatus.failed:
        return TaskStatusOut(status=job.status, error_message=job.error_message)
    if job.status is not JobStatus.completed:
        return TaskStatusOut(status=job.status)

    rows = (
        await session.execute(
            select(Product, ProductImage.filename)
            .outerjoin(ProductImage, ProductImage.product_id == Product.id)
            .where(Product.job_id == job_id)
            .order_by(Product.id)
        )
    ).all()

    data = [
        ProductOut(
            name=product.name,
            price=product.price_text,
            description=product.description,
            image_url=f"{settings.images_base_url}/{filename}" if filename else "",
        )
        for product, filename in rows
    ]
    return TaskStatusOut(status=job.status, data=data)
