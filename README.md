# Web Automation Backend

API REST que automatiza la extracción de datos de productos con **Playwright**, los
normaliza y los persiste en **PostgreSQL**. El scraping corre en un worker separado de la
API, de modo que una petición HTTP nunca espera a que termine un navegador.

## Qué hace

1. **Recibe una tarea** (`POST /tasks`) indicando qué sitio automatizar y, opcionalmente,
   un filtro por nombre de producto. Responde `202 Accepted` con un `job_id`.
2. **Encola el trabajo** en Redis. Un worker lo toma, abre Chromium con Playwright, navega
   el sitio y extrae nombre, precio, descripción e imagen de cada producto.
3. **Normaliza** los datos: colapsa el texto, parsea el precio a `Decimal` + moneda ISO y
   resuelve las URLs relativas de las imágenes.
4. **Descarga las imágenes** a disco y las sirve desde este mismo backend.
5. **Devuelve el resultado** (`GET /tasks/{job_id}`) con el estado del job y, si terminó,
   la lista de productos.

## Tecnologías

| Área | Elección |
| --- | --- |
| Lenguaje | Python 3.12 |
| API | FastAPI + Uvicorn |
| Automatización web | Playwright (Chromium, async) |
| Base de datos | PostgreSQL 16 + SQLAlchemy 2 (async) |
| Migraciones | Alembic |
| Cola de tareas | arq + Redis |
| Validación | Pydantic v2 |
| Logging | structlog (JSON) |
| Dependencias | uv (`pyproject.toml` + `uv.lock`) |
| Contenedores | Docker + Docker Compose |
| Tests | pytest + pytest-asyncio |
| Comandos | Makefile |

## Arquitectura

```
                    ┌──────────────┐        ┌───────────┐
   POST /tasks ───► │     API      │ ─────► │   Redis   │
   GET  /tasks/:id  │  (FastAPI)   │        │  (cola)   │
   GET  /images/*   └──────┬───────┘        └─────┬─────┘
                           │                      │ consume
                           │  lee/escribe         ▼
                           │              ┌───────────────┐
                           │              │    Worker     │
                           │              │  (arq + Play- │
                           │              │   wright)     │
                           │              └───────┬───────┘
                           ▼                      │ escribe
                    ┌─────────────────────────────▼──┐
                    │         PostgreSQL             │
                    │  sites · jobs · products ·     │
                    │  product_images                │
                    └────────────────────────────────┘
                           ▲
                           │ archivos
                    storage/images/
```

La API y el worker corren **la misma imagen** con comandos distintos. La API solo escribe
el job y lo encola; todo el trabajo pesado vive en el worker.

### Estructura de archivos

```
zumma-web-automation/
├── app/
│   ├── main.py                 # Endpoints, lifespan, manejo de errores
│   ├── config.py               # Configuración tipada (pydantic-settings)
│   ├── db.py                   # Engine y sesiones async
│   ├── models.py               # Modelos SQLAlchemy
│   ├── schemas.py              # Contratos de entrada/salida (Pydantic)
│   ├── queue.py                # Cliente de la cola (arq)
│   ├── worker.py               # Proceso worker
│   ├── logging_config.py       # structlog
│   ├── normalization/
│   │   ├── price.py            # "$1.234,50" → Decimal + moneda
│   │   └── text.py             # Limpieza de texto y nombres de archivo seguros
│   ├── scraping/
│   │   ├── runner.py           # Registro de scrapers (única fuente de verdad)
│   │   ├── browser.py          # Ciclo de vida y concurrencia del navegador
│   │   ├── types.py            # ScrapedProduct
│   │   ├── urls.py             # Resolución de URLs relativas
│   │   └── sites/
│   │       ├── saucedemo.py
│   │       └── practice_software_testing.py
│   └── services/
│       ├── tasks.py            # Máquina de estados del job
│       └── images.py           # Descarga y almacenamiento de imágenes
├── migrations/                 # Alembic
├── postman/                    # Colección + environment
├── scripts/smoke_test.sh       # Prueba end-to-end por CLI
├── tests/                      # 92 tests (pytest)
├── storage/images/             # Imágenes descargadas (fuera de git)
├── docker-compose.yml
├── Dockerfile
├── Makefile
└── pyproject.toml / uv.lock
```

## Puesta en marcha

### Requisitos

- Docker y Docker Compose
- Opcional, para desarrollo local: [uv](https://docs.astral.sh/uv/), `make`

### Levantar todo

```bash
git clone https://github.com/SrDefosse/zumma-web-automation
cd zumma-web-automation

cp .env.example .env     # o: make setup
docker compose up -d --build

# Verificar
curl http://localhost:8000/health
```

Con `make` instalado:

```bash
make setup      # crea .env e instala dependencias locales
make up-build   # levanta el stack
make logs       # sigue los logs
make help       # lista todos los comandos
```

Las migraciones de Alembic las aplica el contenedor `api` al arrancar
(`RUN_MIGRATIONS=1`), y el worker espera a que la API esté sana antes de empezar.

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Configuración

Todas las variables tienen un default razonable; `.env.example` las documenta.

| Variable | Default | Descripción |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://webauto:webauto@db:5432/webauto` | Conexión a PostgreSQL |
| `REDIS_URL` | `redis://redis:6379/0` | Conexión a la cola |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Base con la que se construye `image_url` |
| `PLAYWRIGHT_HEADLESS` | `true` | Correr Chromium sin interfaz |
| `PLAYWRIGHT_TIMEOUT_MS` | `15000` | Timeout de navegación y selectores |
| `SCRAPER_MAX_CONCURRENCY` | `2` | Jobs (y navegadores) en paralelo |
| `SAUCEDEMO_USERNAME` / `SAUCEDEMO_PASSWORD` | `standard_user` / `secret_sauce` | Credenciales del login |
| `LOG_LEVEL` | `INFO` | Nivel de log |
| `LOG_JSON` | `true` | JSON en runtime, texto legible si `false` |

> `.env` no está versionado. `.env.example` es la plantilla.

## Endpoints

### `POST /tasks`

Inicia una tarea de automatización.

```http
POST /tasks
Content-Type: application/json

{
  "task_id": "saucedemo",
  "lookup_key": "backpack"
}
```

| Campo | Tipo | Requerido | Descripción |
| --- | --- | --- | --- |
| `task_id` | `"saucedemo"` \| `"practicesoftware"` | sí | Sitio a automatizar |
| `lookup_key` | string | no | Filtro por coincidencia parcial en el nombre (case-insensitive) |

**`202 Accepted`**

```json
{ "job_id": "123e4567-e89b-12d3-a456-426614174000" }
```

| Código | Cuándo |
| --- | --- |
| `202` | Job creado y encolado |
| `422` | `task_id` desconocido, falta un campo o hay campos de más |
| `503` | La cola no está disponible |

### `GET /tasks/{job_id}`

Estado y resultado de una tarea.

**En curso** — `{"status": "pending"}` o `{"status": "in_progress"}`

**Completada**

```json
{
  "status": "completed",
  "data": [
    {
      "name": "Sauce Labs Backpack",
      "price": "$29.99",
      "description": "carry.allTheThings() with the sleek, streamlined Sly Pack...",
      "image_url": "http://localhost:8000/images/Sauce-Labs-Backpack-75a11aed8b615baa.jpg"
    }
  ]
}
```

**Fallida**

```json
{
  "status": "failed",
  "error_message": "RuntimeError: Login rechazado por saucedemo: Epic sadface..."
}
```

| Código | Cuándo |
| --- | --- |
| `200` | Job encontrado |
| `404` | No existe un job con ese id |
| `422` | El id no es un UUID |

### `GET /images/{filename}`

Sirve una imagen descargada. Es la URL que aparece en `image_url`.

### `GET /health`

```json
{ "status": "ok", "database": "ok", "queue": "ok", "time": "2026-10-06T21:30:00Z" }
```

Devuelve `"degraded"` si Postgres o Redis no responden. Lo usa el healthcheck de Compose.

## Sitios soportados

### `saucedemo` — https://www.saucedemo.com/

Hace login con las credenciales de configuración, va al inventario y extrae las 6 cards.
Detecta explícitamente el banner de error del login, así que una credencial mal puesta
produce un `error_message` claro en lugar de un timeout opaco.

### `practicesoftware` — https://practicesoftwaretesting.com/

Recorre el catálogo y las categorías (`hand-tools`, `power-tools`, `other`, `rentals`)
paginando por query param (`?page=N`). El listado no trae la descripción, así que después
visita el detalle de cada producto único, de 4 en 4 en paralelo. Deduplica por id de
producto, porque el mismo artículo aparece en varias categorías.

## Probar la API

### Colección de Postman

`postman/` trae una colección ejecutable de punta a punta y su environment:

1. Importar `postman/zumma-web-automation.postman_collection.json` y
   `postman/local.postman_environment.json` en Postman.
2. Seleccionar el environment **Zumma Web Automation - local**.
3. **Run collection**.

Contiene 13 requests en cuatro carpetas:

| Carpeta | Qué cubre |
| --- | --- |
| **Health** | `GET /` y `GET /health` (verifica Postgres y Redis) |
| **Saucedemo** | `POST /tasks` → guarda el `job_id` → poll automático hasta `completed` → descarga la imagen devuelta |
| **Practice Software Testing** | Igual, con `lookup_key`, y verifica que todos los resultados matcheen el filtro |
| **Errores** | `task_id` inválido, campo de más, body vacío, UUID inexistente, id mal formado, intento de path traversal en `/images` |

El `POST` guarda el `job_id` en una variable de colección y el `GET` siguiente se
reejecuta solo (`pm.execution.setNextRequest`) mientras el job siga en `pending` o
`in_progress`, con un tope de `max_poll_attempts`. Las aserciones verifican el contrato
del challenge producto por producto: las cuatro claves exactas, que `price` tenga dígitos
y que `image_url` sea una URL absoluta de este backend.

Por CLI, con [newman](https://github.com/postmanlabs/newman):

```bash
make postman
# equivale a:
npx newman run postman/zumma-web-automation.postman_collection.json \
  -e postman/local.postman_environment.json --delay-request 3000
```

`--delay-request` es lo que espacia los reintentos del polling.

### Smoke test por CLI

```bash
make smoke                                  # saucedemo, todos los productos
./scripts/smoke_test.sh practicesoftware hammer
```

Crea un job real, espera a que termine y valida la forma de la respuesta.

### curl

```bash
job_id=$(curl -s -X POST http://localhost:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"saucedemo"}' | jq -r .job_id)

curl -s "http://localhost:8000/tasks/$job_id" | jq
```

### Tests

```bash
make test        # 92 tests
make test-cov    # con cobertura
make lint
```

No requieren Docker, Redis ni navegador: corren sobre SQLite en memoria y reemplazan el
scraper, la descarga de imágenes y la cola por dobles. Lo que hace eso posible es que la
extracción está separada de la navegación — los scrapers traen las cards crudas en una
sola evaluación del DOM y el parseo ocurre en funciones puras de Python.

## Modelo de datos

```
sites ──┬──< jobs ──< products ──< product_images
        └──< products
```

| Tabla | Rol |
| --- | --- |
| `sites` | Sitios soportados. `code` es el `task_id` de la API |
| `jobs` | Una ejecución: estado, `lookup_key`, error, `started_at`/`finished_at` |
| `products` | Producto normalizado de un job |
| `product_images` | Imagen descargada (1:1 con el producto) |

Decisiones relevantes:

- **El precio se guarda dos veces, a propósito.** `price_text` conserva lo que publica el
  sitio (es lo que devuelve la API, que el challenge define como string) y
  `price_amount: NUMERIC(12,2)` + `price_currency` son la versión normalizada, consultable
  y comparable. Nunca `float` para dinero.
- **`image_url` no se persiste.** Se guarda el `filename` y la URL absoluta se arma al leer
  con `PUBLIC_BASE_URL`. Así mover el backend a otro host o a HTTPS no invalida las filas.
- **Timestamps con timezone** (`TIMESTAMPTZ`) y defaults del lado de la base.
- **`UNIQUE (job_id, name)`** evita duplicados dentro de un job; el scraper los filtra
  antes para que un nombre repetido no aborte el job entero.
- **Índice en `products.job_id`**, que es la columna por la que filtra el único query de
  lectura.
- **`ON DELETE CASCADE`** de job a productos y a imágenes; `RESTRICT` hacia `sites`.

## Decisiones de diseño

**Cola de tareas en vez de `BackgroundTasks`.** Un job de `practicesoftware` tarda
minutos y abre varios navegadores. Dentro del proceso de uvicorn eso compite con el
tráfico HTTP y se pierde entero si el contenedor se reinicia. Con arq + Redis la cola es
durable, y al arrancar el worker marca como `failed` los jobs que quedaron en
`in_progress` por una caída (los `pending` siguen encolados y se retoman).

**Un solo lugar decide cuántos navegadores existen.** `SCRAPER_MAX_CONCURRENCY` limita a
la vez el paralelismo del worker y un semáforo en `browser.py`. Sin eso, N jobs
simultáneos son N Chromium compitiendo por la memoria del contenedor.

**Extracción separada de la navegación.** Cada scraper hace una única evaluación en el
navegador que devuelve las cards crudas; el parseo, la normalización y el filtrado ocurren
en funciones puras. Es más rápido (un round-trip por página en lugar de uno por campo) y
es lo que hace testeable la parte que más cambia.

**Paginación determinista.** `practicesoftwaretesting.com` pagina por query param, así que
el scraper construye la URL en lugar de clickear "Next" y adivinar si cambió de página.

**Un producto sin imagen sigue siendo un resultado.** Si falla una descarga, el producto se
guarda igual y el `GET` lo devuelve con `image_url` vacío (la consulta usa `LEFT JOIN`). Si
falla el commit, los archivos ya escritos se borran para no dejar huérfanos.

**Nombres de archivo saneados.** El nombre del producto viene de una página externa: es
entrada no confiable. Se convierte a un slug ASCII + hash de la URL, y antes de escribir se
verifica que el destino siga dentro de `storage/images/`.

## Comandos

`make help` los lista todos. Los más usados:

| Comando | Qué hace |
| --- | --- |
| `make up-build` | Reconstruye y levanta el stack |
| `make down` / `make clean` | Baja el stack / lo baja y borra volúmenes e imágenes |
| `make logs-api` / `make logs-worker` | Logs de la API / del worker |
| `make test` / `make lint` | Tests / análisis estático |
| `make smoke` | Job real end-to-end |
| `make postman` | Corre la colección con newman |
| `make migrate` | Aplica migraciones |
| `make migration m="..."` | Genera una migración nueva |
| `make psql` | Abre psql |

## CI

`.github/workflows/ci.yml` corre en cada push: ruff, los 92 tests y una verificación de
que las migraciones aplican y son reversibles. El job end-to-end (stack completo +
colección de Postman con newman) se dispara a mano con `workflow_dispatch`, para que la
caída de un sitio externo no ponga el CI en rojo.

## Troubleshooting

| Síntoma | Qué mirar |
| --- | --- |
| Un job queda en `pending` | ¿Está arriba el worker? `make logs-worker` |
| `/health` devuelve `degraded` | Qué dependencia está en `error`, y después `make logs` |
| Un job falla con timeout | Subir `PLAYWRIGHT_TIMEOUT_MS`; el sitio externo puede estar lento |
| `image_url` apunta al host equivocado | Ajustar `PUBLIC_BASE_URL` en `.env` |
| El worker muere scrapeando | Memoria: bajar `SCRAPER_MAX_CONCURRENCY` |
