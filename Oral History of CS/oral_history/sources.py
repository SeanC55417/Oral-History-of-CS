import json
import re
from pathlib import Path
from urllib.parse import urlsplit

FORMATS = {"html", "pdf"}


def validate_source(source):
    for field in ("id", "title", "url", "format"):
        if not isinstance(source.get(field), str) or not source[field].strip():
            raise ValueError(f"Source needs a nonempty {field}.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", source["id"]):
        raise ValueError("Source IDs may contain lowercase letters, digits, hyphens, and underscores.")
    if source["format"] not in FORMATS:
        raise ValueError("Only html and pdf sources are supported.")
    for field in ("url", "download_url"):
        if field in source and urlsplit(source[field]).scheme not in {"http", "https"}:
            raise ValueError(f"{field} must be an HTTP(S) URL.")
    if source.get("pdf_extraction_mode", "plain") not in {"plain", "layout"}:
        raise ValueError("PDF extraction mode must be plain or layout.")


def load_sources(path):
    sources = json.loads(Path(path).read_text(encoding="utf-8"))
    seen = set()
    for source in sources:
        validate_source(source)
        if source["id"] in seen:
            raise ValueError(f"Duplicate source ID: {source['id']}")
        seen.add(source["id"])
    return sources
