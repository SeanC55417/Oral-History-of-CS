"""Download bytes and preserve a traceable raw copy before extracting text."""
import json
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from pypdf import PdfReader
from .formats import CAPTION_FORMATS, extract_structured

USER_AGENT = "OralHistoryStudentProject/0.1 (educational research)"


def read_url(url, headers=None):
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ValueError("Downloads require an HTTP(S) URL.")
    request = Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urlopen(request, timeout=60) as response:
        return response.read(), {"requested_url": url, "resolved_url": response.geturl(),
                                 "content_type": response.headers.get("Content-Type", "")}


def download_source(source):
    # Keep the walkthrough helper available.
    return read_url(source.get("download_url", source["url"]))[0]


def retrieve_source(source):
    return download_source(source).decode("utf-8")


def archive_details(url):
    match = re.fullmatch(r"https?://web\.archive\.org/web/(\d{14})(?:[a-z]+_)?/(https?://.+)", url)
    if not match:
        raise ValueError("Use a specific Wayback snapshot URL with a 14-digit timestamp.")
    stamp, original = match.groups()
    datetime.strptime(stamp, "%Y%m%d%H%M%S")
    return {"archive_timestamp": stamp, "original_url": original, "archive_url": url}


def fetch_reddit(source):
    parsed = urlsplit(source["url"])
    if parsed.hostname not in {"reddit.com", "www.reddit.com", "old.reddit.com", "oauth.reddit.com"} or "/comments/" not in parsed.path:
        raise ValueError("Use a full Reddit thread URL containing /comments/, or local_path for saved JSON.")
    path = parsed.path.rstrip("/")
    if not path.endswith(".json"):
        path += ".json"
    token = os.environ.get("REDDIT_ACCESS_TOKEN", "").strip()
    host = "oauth.reddit.com" if token else "www.reddit.com"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        return read_url(urlunsplit(("https", host, path, "raw_json=1&limit=100", "")), headers)
    except HTTPError as exc:
        if exc.code in {401, 403, 429}:
            raise ValueError(f"Reddit returned HTTP {exc.code}. Use authorized API access (REDDIT_ACCESS_TOKEN) or a saved thread JSON via local_path.") from None
        raise


def fetch_video(source):
    # A direct caption URL is the lightest and most reproducible option.
    if source.get("transcript_url"):
        content, metadata = read_url(source["transcript_url"])
        subtitle_format = source.get("transcript_format", "vtt")
        kind = source.get("caption_kind", "unspecified")
    else:
        try:
            import yt_dlp
        except ImportError:
            raise ValueError("Video URL import needs: python -m pip install -r requirements-video.txt; alternatively use a local VTT/SRT file.") from None
        language = source.get("language", "en")
        options = {"quiet": True, "noplaylist": True, "skip_download": True,
                   "socket_timeout": 30, "retries": 1}
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(source["url"], download=False)
            if not info or info.get("_type") in {"playlist", "multi_video"}:
                raise ValueError("Supply one video URL, not a playlist.")
            tracks = []
            kind = "manual"
            for key, label in (("subtitles", "manual"), ("automatic_captions", "automatic")):
                if label == "automatic" and not source.get("allow_auto_captions", False):
                    continue
                tracks = (info.get(key) or {}).get(language, [])
                tracks = [t for t in tracks if t.get("ext") in {"vtt", "srt"}]
                if tracks:
                    kind = label
                    break
            if not tracks:
                raise ValueError(f"No {language} VTT/SRT captions available. Provide a transcript, another language, or explicitly allow_auto_captions.")
            track = next((t for t in tracks if t["ext"] == "vtt"), tracks[0])
            with downloader.urlopen(track["url"]) as response:
                content = response.read()
            subtitle_format = track["ext"]
            metadata = {"requested_url": source["url"], "resolved_url": info.get("webpage_url", source["url"]),
                        "video_title": info.get("title"), "video_id": info.get("id")}
    metadata.update({"caption_kind": kind, "language": source.get("language", "en")})
    cached = {"video_url": source["url"], "caption_format": subtitle_format,
              "caption_kind": kind, "language": source.get("language", "en"),
              "captions": content.decode("utf-8-sig")}
    return json.dumps(cached, ensure_ascii=False).encode("utf-8"), metadata


def html_to_text(html, selector=None):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, nav, footer, header, #wm-ipp-base, #wm-ipp-print"):
        tag.decompose()
    content = soup.select_one(selector) if selector else (
        soup.find("div", id="mw-content-text") or soup.find("main") or soup.find("article") or soup.body)
    if content is None:
        raise ValueError("Could not find the page content; check content_selector or use a saved transcript.")
    return content.get_text(separator="\n", strip=True)


def extract_document(content, source):
    source_format = source["format"]
    pages, segments, warnings = [], [], []
    if source_format == "pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("Expected a PDF; supply the actual PDF download_url, not its landing page.")
        reader = PdfReader(BytesIO(content))
        pages = [{"pdf_page": i, "text": page.extract_text(extraction_mode=source.get("pdf_extraction_mode", "plain")) or ""} for i, page in enumerate(reader.pages, 1)]
        text = "\n\n".join(page["text"] for page in pages)
        if any(not p["text"].strip() for p in pages):
            warnings.append("Some PDF pages have no extractable text; inspect for scans needing OCR.")
    elif source_format in {"html", "wayback"}:
        text = html_to_text(content, source.get("content_selector"))
    elif source_format in {"txt", "markdown"}:
        text = content.decode("utf-8-sig")
    elif source_format in CAPTION_FORMATS | {"reddit"}:
        text, segments, warnings = extract_structured(content, source_format)
    else:
        raise ValueError(f"Unsupported format: {source_format}")
    if not text.strip():
        raise ValueError("No text extracted. Scanned PDFs may require OCR.")
    return {"text": text, "pages": pages, "segments": segments, "warnings": warnings}


def extract_content(content, source_format):
    document = extract_document(content, {"format": source_format})
    return document["text"], document["pages"]


def obtain_content(source, root, offline=False, refresh=False):
    path = root / "data/raw" / f"{source['id']}.{source['format']}"
    if path.exists() and not refresh:
        return path.read_bytes(), path
    metadata = {"retrieved_at": datetime.now(timezone.utc).isoformat()}
    if "local_path" in source:
        local = (root / source["local_path"]).resolve()
        if not local.is_relative_to(root.resolve()):
            raise ValueError("local_path must stay inside the project.")
        content = local.read_bytes()
        metadata["local_path"] = source["local_path"]
    elif offline:
        raise ValueError(f"Offline mode: missing raw file {path.name}")
    elif source["format"] == "reddit":
        content, details = fetch_reddit(source)
        metadata.update(details)
    elif source["format"] == "video":
        content, details = fetch_video(source)
        metadata.update(details)
    else:
        content, details = read_url(source.get("download_url", source["url"]))
        metadata.update(details)
    if source["format"] == "wayback":
        metadata.update(archive_details(metadata.get("resolved_url", source["url"])))
    extract_document(content, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.with_name(path.name + ".retrieval.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return content, path
