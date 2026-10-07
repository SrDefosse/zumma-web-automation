from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AsyncSessionLocal, engine, get_session
from app.logging_config import configure_logging, get_logger
from app.queue import close_queue, enqueue_scrape, init_queue, queue_is_healthy
from app.schemas import HealthOut, TaskAccepted, TaskCreate, TaskStatusOut
from app.scraping.runner import UnsupportedTaskError
from app.services.tasks import create_job, get_job_result, seed_sites

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Reemplaza a @app.on_event, deprecado desde FastAPI 0.100.

    El esquema lo crean las migraciones de Alembic (entrypoint.sh), no la aplicacion;
    aca solo se siembran los sitios soportados y se abre la conexion a la cola.
    """
    configure_logging()
    settings.images_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as session:
        await seed_sites(session)
    await init_queue()
    log.info("api iniciada", public_base_url=settings.public_base_url)

    yield

    await close_queue()
    await engine.dispose()
    log.info("api detenida")


app = FastAPI(
    title="Web Automation API",
    version="1.0.0",
    description=(
        "Automatiza la extraccion de productos con Playwright, los normaliza y los "
        "persiste en PostgreSQL. El scraping corre en un worker aparte."
    ),
    lifespan=lifespan,
)

app.mount("/images", StaticFiles(directory=settings.images_dir), name="images")


@app.exception_handler(UnsupportedTaskError)
async def unsupported_task_handler(request: Request, exc: UnsupportedTaskError) -> JSONResponse:
    """Un task_id no soportado es un error del cliente, no un 500."""
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "Web Automation API", "docs": "/docs", "health": "/health"}


@app.get("/health", response_model=HealthOut, tags=["health"])
async def health(session: AsyncSession = Depends(get_session)) -> HealthOut:
    """Comprueba dependencias externas. Lo usa el healthcheck de Docker Compose."""
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # noqa: BLE001 - el health check reporta, no falla
        log.warning("postgres no responde", error=str(exc))
        database = "error"

    queue = "ok" if await queue_is_healthy() else "error"
    overall = "ok" if database == "ok" and queue == "ok" else "degraded"
    return HealthOut(status=overall, database=database, queue=queue, time=datetime.now(UTC))


@app.post(
    "/tasks",
    response_model=TaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["tasks"],
    summary="Inicia una tarea de automatizacion",
)
async def post_tasks(
    payload: TaskCreate, session: AsyncSession = Depends(get_session)
) -> TaskAccepted:
    job_id = await create_job(session, payload.task_id.value, payload.lookup_key)
    try:
        await enqueue_scrape(job_id)
    except Exception as exc:  # noqa: BLE001 - sin cola el job no se puede ejecutar
        log.error("no se pudo encolar el job", job_id=str(job_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La cola de tareas no esta disponible, reintenta mas tarde",
        ) from exc
    return TaskAccepted(job_id=job_id)


@app.get(
    "/tasks/{job_id}",
    response_model=TaskStatusOut,
    response_model_exclude_none=True,
    tags=["tasks"],
    summary="Estado y resultado de una tarea",
)
async def get_task(job_id: UUID, session: AsyncSession = Depends(get_session)) -> TaskStatusOut:
    result = await get_job_result(session, job_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return result
