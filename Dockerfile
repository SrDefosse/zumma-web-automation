# Imagen oficial de Playwright: ya trae chromium y todas las librerias del sistema.
# La version de la imagen debe coincidir con la de playwright en pyproject.toml.
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.5.9 /uv /usr/local/bin/uv

WORKDIR /app

# Capa de dependencias separada del codigo: cambiar un .py no reinstala todo.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini entrypoint.sh ./
COPY migrations ./migrations
COPY app ./app

RUN chmod +x entrypoint.sh \
    && mkdir -p storage/images \
    && chown -R pwuser:pwuser /app /opt/venv

# El contenedor no necesita root una vez instaladas las dependencias.
USER pwuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
