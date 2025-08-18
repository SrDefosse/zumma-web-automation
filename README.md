# Web Automation Backend

API REST para automatización de extracción de datos de sitios web utilizando Playwright. Este proyecto permite extraer información de productos de diferentes sitios web de manera automatizada y almacenarla en una base de datos PostgreSQL.

## Descripción General

El sistema automatiza el proceso de:
1. **Navegación web**: Utiliza Playwright para navegar sitios web de forma automatizada
2. **Extracción de datos**: Obtiene información de productos (nombre, precio, descripción, imágenes)
3. **Normalización**: Convierte los datos a un formato estándar
4. **Almacenamiento**: Guarda la información en PostgreSQL con un esquema normalizado
5. **Descarga de imágenes**: Almacena las imágenes localmente y las sirve desde el backend

## Tecnologías

- **Backend**: Python 3.12 + FastAPI
- **Automatización Web**: Playwright
- **Base de Datos**: PostgreSQL 16
- **ORM**: SQLAlchemy
- **Contenedorización**: Docker + Docker Compose
- **Validación**: Pydantic
- **Cliente HTTP**: httpx

## Arquitectura de archivos

```
zumma-web-automation/
├── app/
│   ├── main.py              # API
│   ├── models.py            # Modelos de base de datos
│   ├── schemas.py           # Esquemas de validación
│   ├── config.py            # Configuración
│   ├── db.py                # Conexión a base de datos
│   ├── scraping/
│   │   ├── runner.py        # Orquestador de scrapers
│   │   └── sites/
│   │       ├── saucedemo.py # Scraper para Saucedemo
│   │       └── practice_software_testing.py # Scraper para Practice Software Testing
│   └── services/
│       ├── tasks.py         # Lógica de jobs/tareas
│       └── images.py        # Descarga y gestión de imágenes
├── storage/images/          # Imágenes descargadas
├── docker-compose.yml       # Configuración de contenedores
├── Dockerfile              # Imagen de la aplicación
└── requirements.txt        # Dependencias
```

## Sitios Web Soportados

### 1. Saucedemo
- **URL**: https://www.saucedemo.com/
- **task_id**: `saucedemo`
- **Funcionalidad**: 
  - Login automático con credenciales `standard_user/secret_sauce`
  - Extracción de todos los productos del catálogo
  - Filtrado opcional por lookup key

### 2. Practice Software Testing
- **URL**: https://practicesoftwaretesting.com/
- **task_id**: `practicesoftware`
- **Funcionalidad**:
  - Navegación por categorías (hand-tools, power-tools, etc.)
  - Paginación automática
  - Extracción detallada visitando página individual de cada producto

## Endpoints de la API

### POST /tasks
Inicia una nueva tarea de automatización web.

**Request Body:**
```json
{
  "task_id": "saucedemo",
  "lookup_key": "sauce labs backpack"
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

### GET /tasks/{job_id}
Obtiene el estado y resultados de una tarea específica.

**Estados:**
- `pending`: Tarea creada, esperando procesamiento
- `in_progress`: Scraping en ejecucion
- `completed`: Completada exitosamente
- `failed`: Error durante el procesamiento

**Response - Tarea Completada:**
```json
{
  "status": "completed",
  "data": [
    {
      "name": "Sauce Labs Backpack",
      "price": "$29.99",
      "description": "carry.allTheThings() with the sleek, streamlined Sly Pack...",
      "image_url": "/images/Sauce-Labs-Backpack-75a11aed8b615baa.jpg"
    }
  ]
}
```

**Response - Tarea Fallida:**
```json
{
  "status": "failed",
  "error_message": "Error detallado del problema"
}
```

### GET /images/{filename}
Sirve las imagenes descargadas desde el backend.

**Ejemplo:**
```
GET /images/Sauce-Labs-Backpack-75a11aed8b615baa.jpg
```

## Instalación y Ejecución

### Prerrequisitos
- Docker
- Docker Compose

### Pasos para ejecutar

1. **Clonar el repositorio:**
```bash
git clone https://github.com/SrDefosse/zumma-web-automation
cd zumma-web-automation
```

2. **Levantar el proyecto con Docker Compose:**
```bash
docker-compose up --build
```

3. **Verificar que la API está funcionando:**
```bash
curl http://localhost:8000
```

4. **Acceder a la documentación automática:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Variables de Entorno (Opcional)

Crear un archivo `.env` para personalizar la configuración:
```env
DATABASE_URL=postgresql+asyncpg://webauto:webauto@db:5432/webauto
PLAYWRIGHT_HEADLESS=true
```

## Ejemplos de Uso

### 1. Extraer todos los productos de Saucedemo
```bash
# crear task
curl -X POST "http://localhost:8000/tasks" \
  -H "Content-Type: application/json" \
  -d '{"task_id": "saucedemo"}'

# respuesta: {"job_id": "abc-123-def"}

# consulta de resultado
curl "http://localhost:8000/tasks/abc-123-def"
```

### 2. Buscar producto específico en Practice Software Testing
```bash
# con filtro
curl -X POST "http://localhost:8000/tasks" \
  -H "Content-Type: application/json" \
  -d '{"task_id": "practicesoftware", "lookup_key": "hammer"}'

# consulta de resultado
curl "http://localhost:8000/tasks/abc-123-def"
```

## Estructura de Base de Datos

El proyecto tiene un esquema normalizado con las siguientes tablas:

- **`sites`**: Sitios web soportados
- **`jobs`**: Registro de tareas de scraping
- **`products`**: Información de productos extraídos
- **`product_images`**: Metadatos de imágenes descargadas

## 🔧 Comandos Útiles para Desarrollo

### Iniciar el proyecto (primera vez o después de cambios)
```bash
docker-compose up --build
```

### Iniciar solo si ya está construido
```bash
docker-compose up
```

### Reconstruir solo la aplicación (tras cambios en código)
```bash
docker-compose up --build api
```

### Ejecutar en background (libera la terminal)
```bash
docker-compose up -d
```

### Ver logs en tiempo real
```bash
docker-compose logs -f api
```

### Ver logs de la base de datos
```bash
docker-compose logs -f db
```

### Parar todos los contenedores
```bash
docker-compose down
```

### Parar y limpiar todo (incluyendo volúmenes)
```bash
docker-compose down -v
```

### Acceder al contenedor de la aplicación
```bash
docker-compose exec api bash
```

### Ver estado de los contenedores
```bash
docker-compose ps
```

### Reiniciar solo la aplicación
```bash
docker-compose restart api
```

## Características Técnicas

### Async/Await
- Toda la aplicación utiliza programación asíncrona
- No bloquea el servidor durante el scraping

### Gestión de Imágenes
- Descarga automática de imágenes de productos
- Almacenamiento local con nombres únicos (hash-based)
- Servicio de imágenes integrado en la API

### Manejo de Errores
- Captura y registro de errores durante el scraping
- Estados de fallo informativos
- Timeout y reintentos automáticos

### Normalización de Datos
- Formato JSON consistente independientemente del sitio
- Validación de datos con Pydantic
- Esquema de base de datos flexible para diferentes tipos de productos

## Soporte

Si encuentras algún problema o tienes preguntas sobre la implementación, puedes:
1. Revisar los logs: `docker-compose logs`
2. Verificar que todos los contenedores estén ejecutándose: `docker-compose ps`
3. Reiniciar el sistema: `docker-compose down && docker-compose up --build`
