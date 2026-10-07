.DEFAULT_GOAL := help
.PHONY: help setup up up-build down clean logs logs-api logs-worker ps shell psql \
        migrate migration test test-cov lint fmt smoke postman

COMPOSE := docker compose

help: ## Lista los comandos disponibles
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- Entorno ---------------------------------------------------------------

setup: ## Crea .env a partir de .env.example e instala dependencias locales
	@test -f .env || cp .env.example .env
	uv sync

# --- Docker ----------------------------------------------------------------

up: ## Levanta todo el stack en background
	$(COMPOSE) up -d

up-build: ## Reconstruye las imagenes y levanta el stack
	$(COMPOSE) up -d --build

down: ## Detiene el stack
	$(COMPOSE) down

clean: ## Detiene el stack y borra volumenes e imagenes descargadas
	$(COMPOSE) down -v
	rm -rf storage/images/*.jpg storage/images/*.png storage/images/*.webp

logs: ## Sigue los logs de todos los servicios
	$(COMPOSE) logs -f

logs-api: ## Sigue los logs de la API
	$(COMPOSE) logs -f api

logs-worker: ## Sigue los logs del worker de scraping
	$(COMPOSE) logs -f worker

ps: ## Estado de los contenedores
	$(COMPOSE) ps

shell: ## Abre una shell en el contenedor de la API
	$(COMPOSE) exec api bash

psql: ## Abre psql en la base de datos
	$(COMPOSE) exec db psql -U webauto -d webauto

# --- Base de datos ---------------------------------------------------------

migrate: ## Aplica las migraciones pendientes
	$(COMPOSE) exec api alembic upgrade head

migration: ## Genera una migracion nueva: make migration m="descripcion"
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(m)"

# --- Calidad ---------------------------------------------------------------

test: ## Corre la suite de tests
	uv run pytest -q

test-cov: ## Corre los tests con reporte de cobertura
	uv run pytest --cov=app --cov-report=term-missing

lint: ## Analisis estatico
	uv run ruff check app tests

fmt: ## Formatea el codigo
	uv run ruff format app tests
	uv run ruff check --fix app tests

# --- Pruebas de la API -----------------------------------------------------

smoke: ## Lanza un job real contra saucedemo y espera el resultado
	./scripts/smoke_test.sh

postman: ## Corre la coleccion de Postman con newman (requiere npx)
	npx -y newman run postman/zumma-web-automation.postman_collection.json \
		-e postman/local.postman_environment.json
