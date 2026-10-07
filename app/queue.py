"""Cola de tareas (arq sobre Redis).

Separar la API del scraping es necesario, no cosmetico: un job de
practicesoftwaretesting tarda minutos y abre varios navegadores. Con BackgroundTasks
eso corria dentro del proceso de uvicorn, competia con el trafico HTTP y se perdia
entero si el contenedor se reiniciaba.
"""

from uuid import UUID

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import settings
from app.logging_config import get_logger

log = get_logger(__name__)

SCRAPE_TASK = "run_scrape_job"

_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def init_queue() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def close_queue() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


def get_queue() -> ArqRedis:
    if _pool is None:
        raise RuntimeError("La cola no esta inicializada")
    return _pool


async def enqueue_scrape(job_id: UUID) -> None:
    """Encola un job. `_job_id` hace la operacion idempotente ante reintentos del cliente."""
    await get_queue().enqueue_job(SCRAPE_TASK, job_id, _job_id=f"scrape:{job_id}")
    log.info("job encolado", job_id=str(job_id))


async def queue_is_healthy() -> bool:
    try:
        await get_queue().ping()
        return True
    except Exception as exc:  # noqa: BLE001 - el health check reporta, no falla
        log.warning("redis no responde", error=str(exc))
        return False
