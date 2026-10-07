"""Tests de la descarga y el almacenamiento de imagenes."""

import httpx
import pytest

from app.services.images import (
    ImageDownloadError,
    build_filename,
    delete_image,
    download_image,
)

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a"
    "49444154789c6300010000050001"
)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_build_filename_usa_la_extension_del_content_type():
    name = build_filename("Claw Hammer", "https://x.test/img", "image/png")
    assert name.startswith("Claw-Hammer-")
    assert name.endswith(".png")


def test_build_filename_cae_a_la_extension_de_la_url():
    assert build_filename("Claw Hammer", "https://x.test/img.webp?v=2").endswith(".webp")


def test_build_filename_es_determinista_y_distingue_urls():
    primero = build_filename("Hammer", "https://x.test/a.jpg")
    assert primero == build_filename("Hammer", "https://x.test/a.jpg")
    assert primero != build_filename("Hammer", "https://x.test/b.jpg")


def test_build_filename_neutraliza_nombres_hostiles():
    name = build_filename("../../etc/passwd", "https://x.test/a.jpg")
    assert "/" not in name and ".." not in name.split("-")[0]


async def test_download_image_guarda_el_archivo_y_sus_metadatos(images_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=PNG_BYTES, headers={"content-type": "image/png"})

    async with _client(handler) as client:
        stored = await download_image("https://x.test/a.png", "Claw Hammer", client=client)

    assert stored.content_type == "image/png"
    assert stored.size_bytes == len(PNG_BYTES)
    assert stored.filename.endswith(".png")
    archivo = images_dir / stored.filename
    assert archivo.read_bytes() == PNG_BYTES


async def test_download_image_escribe_dentro_del_directorio_de_imagenes(images_dir):
    """Un nombre de producto hostil no debe poder escribir fuera de storage/images."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=PNG_BYTES, headers={"content-type": "image/png"})

    async with _client(handler) as client:
        stored = await download_image("https://x.test/a.png", "../../../evil", client=client)

    assert (images_dir / stored.filename).exists()
    assert images_dir.resolve() in (images_dir / stored.filename).resolve().parents


async def test_download_image_rechaza_content_type_no_imagen(images_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"<html>login</html>", headers={"content-type": "text/html"}
        )

    async with _client(handler) as client:
        with pytest.raises(ImageDownloadError, match="Content-Type"):
            await download_image("https://x.test/a.jpg", "Hammer", client=client)

    assert list(images_dir.iterdir()) == []


async def test_download_image_rechaza_respuesta_vacia(images_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"", headers={"content-type": "image/jpeg"})

    async with _client(handler) as client:
        with pytest.raises(ImageDownloadError, match="vacia"):
            await download_image("https://x.test/a.jpg", "Hammer", client=client)


async def test_download_image_propaga_errores_http_como_image_download_error(images_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _client(handler) as client:
        with pytest.raises(ImageDownloadError):
            await download_image("https://x.test/a.jpg", "Hammer", client=client)


async def test_download_image_rechaza_url_vacia(images_dir):
    with pytest.raises(ImageDownloadError, match="vacia"):
        await download_image("", "Hammer")


def test_delete_image_es_idempotente(images_dir):
    archivo = images_dir / "x.jpg"
    archivo.write_bytes(PNG_BYTES)

    delete_image(str(archivo))
    assert not archivo.exists()
    delete_image(str(archivo))
