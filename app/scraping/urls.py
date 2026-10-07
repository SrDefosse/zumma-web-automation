from urllib.parse import urljoin


def absolutize(base_url: str, raw_url: str | None) -> str:
    """Convierte un src/href relativo en absoluto.

    Cubre los tres casos que aparecen en los sitios soportados: protocol-relative
    ("//cdn/x.jpg"), root-relative ("/img/x.jpg") y relativo ("img/x.jpg").
    """
    if not raw_url:
        return ""
    candidate = raw_url.strip()
    if not candidate:
        return ""
    if candidate.startswith("//"):
        scheme = base_url.split("://", 1)[0] if "://" in base_url else "https"
        return f"{scheme}:{candidate}"
    if candidate.startswith(("http://", "https://")):
        return candidate
    return urljoin(base_url.rstrip("/") + "/", candidate.lstrip("/"))
