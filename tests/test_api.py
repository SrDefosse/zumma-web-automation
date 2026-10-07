"""Tests de integracion de la API contra una base SQLite en memoria.

No se levanta ni Redis ni un navegador: la cola se reemplaza por un doble que registra
los encolados, y los productos se insertan directamente para ejercitar el GET.
"""

from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import main
from app.db import get_session
from app.models import Base, Job, JobStatus, Product, ProductImage, Site


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                Site(
                    id=1, code="saucedemo", name="Saucedemo", base_url="https://www.saucedemo.com"
                ),
                Site(
                    id=2,
                    code="practicesoftware",
                    name="Practice Software Testing",
                    base_url="https://practicesoftwaretesting.com",
                ),
            ]
        )
        await session.commit()

    yield factory
    await engine.dispose()


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[UUID]:
    """Reemplaza la cola por un doble que solo registra los job_id encolados."""
    registro: list[UUID] = []

    async def fake_enqueue(job_id: UUID) -> None:
        registro.append(job_id)

    monkeypatch.setattr(main, "enqueue_scrape", fake_enqueue)
    return registro


@pytest.fixture
async def client(session_factory, enqueued) -> AsyncIterator[AsyncClient]:
    async def override_get_session():
        async with session_factory() as session:
            yield session

    main.app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
    main.app.dependency_overrides.clear()


async def test_post_tasks_devuelve_202_y_encola(client, enqueued):
    response = await client.post("/tasks", json={"task_id": "saucedemo"})

    assert response.status_code == 202
    job_id = UUID(response.json()["job_id"])
    assert enqueued == [job_id]


async def test_post_tasks_acepta_lookup_key(client, session_factory):
    response = await client.post(
        "/tasks", json={"task_id": "practicesoftware", "lookup_key": "  hammer  "}
    )

    assert response.status_code == 202
    async with session_factory() as session:
        job = await session.get(Job, UUID(response.json()["job_id"]))
        assert job.lookup_key == "hammer"
        assert job.status is JobStatus.pending


async def test_post_tasks_convierte_lookup_key_vacio_en_null(client, session_factory):
    response = await client.post("/tasks", json={"task_id": "saucedemo", "lookup_key": "   "})

    async with session_factory() as session:
        job = await session.get(Job, UUID(response.json()["job_id"]))
        assert job.lookup_key is None


async def test_post_tasks_rechaza_task_id_desconocido(client, enqueued):
    """Un task_id desconocido es un error del cliente: lo rechaza el schema, no un 500."""
    response = await client.post("/tasks", json={"task_id": "mercadolibre"})

    assert response.status_code == 422
    assert "saucedemo" in response.text
    assert enqueued == []


async def test_post_tasks_rechaza_campos_desconocidos(client):
    response = await client.post("/tasks", json={"task_id": "saucedemo", "limite": 5})
    assert response.status_code == 422


async def test_post_tasks_rechaza_body_incompleto(client):
    response = await client.post("/tasks", json={})
    assert response.status_code == 422
    assert "task_id" in response.text


async def test_post_tasks_devuelve_503_si_la_cola_falla(client, monkeypatch):
    async def enqueue_roto(job_id: UUID) -> None:
        raise ConnectionError("redis caido")

    monkeypatch.setattr(main, "enqueue_scrape", enqueue_roto)
    response = await client.post("/tasks", json={"task_id": "saucedemo"})

    assert response.status_code == 503
    assert "cola" in response.json()["detail"].lower()


async def test_get_task_inexistente_devuelve_404(client):
    response = await client.get(f"/tasks/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


async def test_get_task_con_id_no_uuid_devuelve_422(client):
    response = await client.get("/tasks/no-es-un-uuid")
    assert response.status_code == 422


@pytest.mark.parametrize("status", [JobStatus.pending, JobStatus.in_progress])
async def test_get_task_en_curso_solo_devuelve_el_estado(client, session_factory, status):
    job_id = uuid4()
    async with session_factory() as session:
        session.add(Job(id=job_id, site_id=1, status=status))
        await session.commit()

    response = await client.get(f"/tasks/{job_id}")

    assert response.status_code == 200
    assert response.json() == {"status": status.value}


async def test_get_task_fallido_devuelve_el_error(client, session_factory):
    job_id = uuid4()
    async with session_factory() as session:
        session.add(
            Job(id=job_id, site_id=1, status=JobStatus.failed, error_message="Login rechazado")
        )
        await session.commit()

    response = await client.get(f"/tasks/{job_id}")

    assert response.status_code == 200
    assert response.json() == {"status": "failed", "error_message": "Login rechazado"}


async def test_get_task_completado_devuelve_el_contrato_del_challenge(client, session_factory):
    job_id = uuid4()
    async with session_factory() as session:
        session.add(Job(id=job_id, site_id=1, status=JobStatus.completed))
        product = Product(
            site_id=1,
            job_id=job_id,
            name="Sauce Labs Backpack",
            description="carry.allTheThings()",
            price_text="$29.99",
            price_amount=Decimal("29.99"),
            price_currency="USD",
        )
        session.add(product)
        await session.flush()
        session.add(
            ProductImage(
                product_id=product.id,
                filename="Sauce-Labs-Backpack-abc123.jpg",
                file_path="storage/images/Sauce-Labs-Backpack-abc123.jpg",
            )
        )
        await session.commit()

    response = await client.get(f"/tasks/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert "error_message" not in body
    assert body["data"] == [
        {
            "name": "Sauce Labs Backpack",
            "price": "$29.99",
            "description": "carry.allTheThings()",
            "image_url": "http://testserver/images/Sauce-Labs-Backpack-abc123.jpg",
        }
    ]


async def test_get_task_completado_incluye_productos_sin_imagen(client, session_factory):
    """La consulta usa LEFT JOIN: un producto cuya imagen fallo no debe desaparecer."""
    job_id = uuid4()
    async with session_factory() as session:
        session.add(Job(id=job_id, site_id=1, status=JobStatus.completed))
        con_imagen = Product(
            site_id=1, job_id=job_id, name="Con imagen", description="", price_text="$1.00"
        )
        sin_imagen = Product(
            site_id=1, job_id=job_id, name="Sin imagen", description="", price_text="$2.00"
        )
        session.add_all([con_imagen, sin_imagen])
        await session.flush()
        session.add(
            ProductImage(
                product_id=con_imagen.id, filename="a.jpg", file_path="storage/images/a.jpg"
            )
        )
        await session.commit()

    body = (await client.get(f"/tasks/{job_id}")).json()

    assert [p["name"] for p in body["data"]] == ["Con imagen", "Sin imagen"]
    assert body["data"][1]["image_url"] == ""


async def test_get_task_solo_devuelve_los_productos_de_su_job(client, session_factory):
    """Dos jobs del mismo sitio no deben mezclar resultados."""
    job_a, job_b = uuid4(), uuid4()
    async with session_factory() as session:
        session.add_all(
            [
                Job(id=job_a, site_id=1, status=JobStatus.completed),
                Job(id=job_b, site_id=1, status=JobStatus.completed),
                Product(site_id=1, job_id=job_a, name="De A", description="", price_text="$1.00"),
                Product(site_id=1, job_id=job_b, name="De B", description="", price_text="$2.00"),
            ]
        )
        await session.commit()

    body = (await client.get(f"/tasks/{job_a}")).json()
    assert [p["name"] for p in body["data"]] == ["De A"]


async def test_root_informa_donde_estan_los_docs(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


async def test_openapi_documenta_los_dos_endpoints(client):
    schema = (await client.get("/openapi.json")).json()
    assert "/tasks" in schema["paths"]
    assert "/tasks/{job_id}" in schema["paths"]
