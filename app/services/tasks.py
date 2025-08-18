from uuid import UUID, uuid4
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import AsyncSessionLocal, engine
from app.models import Base, Job, Site, Product, ProductImage, JobStatus
from app.scraping.runner import run_scraper
from app.services.images import download_image
from datetime import datetime
from sqlalchemy import text

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # sembrar sites
    async with AsyncSessionLocal() as s:
        for code, name in [("saucedemo", "Saucedemo"), ("practicesoftware", "Practice Software Testing")]:
            exists = (await s.execute(select(Site).where(Site.code == code))).scalar_one_or_none()
            if not exists:
                s.add(Site(code=code, name=name))
        await s.commit()

async def create_job(task_id: str, lookup_key: str | None) -> UUID:
    async with AsyncSessionLocal() as s:
        site = (await s.execute(select(Site).where(Site.code == task_id))).scalar_one_or_none()
        if not site:
            raise ValueError("Unsupported task_id")
        job = Job(site_id=site.id, lookup_key=lookup_key, status=JobStatus.pending)
        s.add(job)
        await s.commit()
        await s.refresh(job)
        return job.id

async def run_job(job_id: UUID):
    async with AsyncSessionLocal() as s:
        job = await s.get(Job, job_id)
        if not job: return
        job.status = JobStatus.in_progress
        job.updated_at = datetime.utcnow()
        await s.commit()

    try:
        rows = await run_scraper(task_id=(await get_task_id(job_id)), lookup_key=(await get_lookup_key(job_id)))
        # guarda en DB
        async with AsyncSessionLocal() as s:
            job = await s.get(Job, job_id)
            for r in rows:
                # descarga imagen y guarda product + image
                fp, served = await download_image(r["image_url"], r["name"])
                p = Product(
                    site_id=job.site_id,
                    job_id=job.id,
                    name=r["name"],
                    description=r["description"],
                    price_text=r["price"],
                )
                s.add(p)
                await s.flush()
                s.add(ProductImage(product_id=p.id, file_path=fp, served_url=served))
            job.status = JobStatus.completed
            job.updated_at = datetime.utcnow()
            await s.commit()
    except Exception as e:
        async with AsyncSessionLocal() as s:
            job = await s.get(Job, job_id)
            job.status = JobStatus.failed
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()
            await s.commit()

async def get_task_id(job_id: UUID) -> str:
    async with AsyncSessionLocal() as s:
        stmt = select(Job, Site).join(Site, Job.site_id == Site.id).where(Job.id == job_id)
        row = (await s.execute(stmt)).first()
        return row[1].code

async def get_lookup_key(job_id: UUID) -> str | None:
    async with AsyncSessionLocal() as s:
        job = await s.get(Job, job_id)
        return job.lookup_key

async def get_job_result(job_id: UUID):
    async with AsyncSessionLocal() as s:
        job = await s.get(Job, job_id)
        if not job: return None
        if job.status != JobStatus.completed:
            return {"status": job.status.value} if job.status != JobStatus.failed else {
                "status": "failed", "error_message": job.error_message
            }
        # construye la salida solicitada filtrando por job_id
        stmt = text("""
          SELECT p.name, p.price_text AS price, p.description, i.served_url AS image_url
          FROM products p
          JOIN product_images i ON i.product_id = p.id
          WHERE p.job_id = :job_id
          ORDER BY p.id ASC
        """)
        rows = (await s.execute(stmt, {"job_id": job_id})).mappings().all()
        return {"status": "completed", "data": [dict(r) for r in rows]}
