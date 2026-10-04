import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from .formats import FORMATS


def validate_source(source):
    for field in ("id", "title", "url", "format"):
        if not isinstance(source.get(field), str) or not source[field].strip():
            raise ValueError(f"Source needs a nonempty {field}.")
        
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", source["id"]):
        raise ValueError(f"Invalid source ID: {source['id']}")
    
    if source["format"] not in FORMATS:
        raise ValueError(f"Unsupported format for {source['id']}")
    
    for field in ("url", "download_url", "transcript_url"):
        if field in source and urlsplit(source[field]).scheme not in {"http", "https"}:
            raise ValueError(f"{field} must be an HTTP(S) URL.")
        
    if source["format"] == "wayback":
        from .retrieve import archive_details
        archive_details(source["url"])

    if "authors" in source and (not isinstance(source["authors"], list) or
            any(not isinstance(a, str) or not a.strip() for a in source["authors"])):
        raise ValueError("authors must be a list of names.")
    
    if "allow_auto_captions" in source and type(source["allow_auto_captions"]) is not bool:
        raise ValueError("allow_auto_captions must be true or false.")


def load_sources(path):
    sources = json.loads(Path(path).read_text(encoding="utf-8"))
    seen = set()
    for source in sources:
        validate_source(source)
        if source["id"] in seen:
            raise ValueError(f"Duplicate source ID: {source['id']}")
        seen.add(source["id"])
    return sources
