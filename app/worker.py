"""Worker de arq: consume la cola y ejecuta los jobs de scraping.

Se arranca con `arq app.worker.WorkerSettings` (ver el servicio `worker` en docker-compose).
"""

from uuid import UUID

from arq import func

from app.config import settings
from app.db import engine
from app.logging_config import configure_logging, get_logger
from app.queue import SCRAPE_TASK, redis_settings
from app.services.tasks import recover_stale_jobs, run_job

log = get_logger(__name__)


async def run_scrape_job(ctx: dict, job_id: UUID | str) -> None:
    """Handler de la cola. run_job nunca propaga: el resultado vive en el estado del job."""
    await run_job(UUID(str(job_id)))


async def startup(ctx: dict) -> None:
    configure_logging()
    recovered = await recover_stale_jobs()
    log.info(
        "worker iniciado",
        max_jobs=settings.scraper_max_concurrency,
        jobs_recuperados=recovered,
    )


async def shutdown(ctx: dict) -> None:
    await engine.dispose()
    log.info("worker detenido")


class WorkerSettings:
    functions = [func(run_scrape_job, name=SCRAPE_TASK)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    max_jobs = settings.scraper_max_concurrency
    job_timeout = 900
    max_tries = 1
    keep_result = 3600
