import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("LOG_JSON", "false")

import pytest  # noqa: E402


@pytest.fixture
def images_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige el directorio de imagenes a un tmp_path para no tocar storage/."""
    from app.config import settings

    target = tmp_path / "images"
    target.mkdir()
    monkeypatch.setattr(settings, "images_dir", target)
    return target
