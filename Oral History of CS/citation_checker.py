"""Local citation-support prototype for the project's saved sources."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from typesafe_sdk import Noul, TypeSafeClient

from oral_history.sources import load_sources


ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data/processed"
MEDFORD = ROOT / "output/medford"
PAGE = ROOT / "web/citation_checker.html"
MAX_CLAIM = 1000
MAX_EXCERPT = 10000


class InputError(ValueError):
    pass


def sources_by_id():
    return {source["id"]: source for source in load_sources(ROOT / "data/sources.json")}


def public_source(source):
    if source["format"] == "pdf":
        locator_type, locator = "pdf_page", None
    elif "message_id" in source:
        locator_type, locator = "message_id", source["message_id"]
    elif "x_post_id" in source:
        locator_type, locator = "x_post_id", source["x_post_id"]
    else:
        locator_type, locator = "document", None
    return {
        "id": source["id"],
        "title": source["title"],
        "url": source["url"],
        "date": source.get("publication_date") or (source.get("interview_dates") or [""])[0],
        "locator_type": locator_type,
        "locator": locator,
    }


def resolve_passage(source_id, locator):
    source = sources_by_id().get(source_id)
    if source is None:
        raise InputError("Choose a source from the list.")

    info = public_source(source)
    locator = str(locator or "").strip()
    if info["locator_type"] == "pdf_page":
        if not locator.isdecimal() or int(locator) < 1:
            raise InputError("Enter a valid PDF page number, counting from page 1 of the file.")
        pages_path = PROCESSED / f"{source_id}-pages.json"
        if not pages_path.exists():
            raise InputError("Extracted PDF pages are missing. Run the project pipeline first.")
        pages = json.loads(pages_path.read_text(encoding="utf-8"))
        page = int(locator)
        if page > len(pages):
            raise InputError(f"This PDF has {len(pages)} pages; page {page} does not exist.")
        passage = pages[page - 1]["text"]
        location = f"PDF page {page}"
    else:
        expected = str(info["locator"] or "")
        if locator != expected:
            if expected:
                raise InputError(f"This source is archived as post/message ID {expected}.")
            raise InputError("This source has no page or message ID; leave Location blank.")
        text_path = PROCESSED / f"{source_id}.txt"
        if not text_path.exists():
            raise InputError("Extracted source text is missing. Run the project pipeline first.")
        passage = text_path.read_text(encoding="utf-8")
        location = (
            f"Message ID {expected}" if info["locator_type"] == "message_id"
            else f"Post ID {expected}" if info["locator_type"] == "x_post_id"
            else "Document text"
        )

    if not passage.strip():
        raise InputError("No text was extracted at this location.")
    return info, location, passage


def normalized(text):
    return " ".join(text.split())


def validate_excerpt(excerpt, passage):
    excerpt = str(excerpt or "").strip()
    if not excerpt:
        raise InputError("Select or paste a passage from the displayed source text.")
    if len(excerpt) > MAX_EXCERPT:
        raise InputError("Choose a shorter passage (10,000 characters or fewer).")
    if normalized(excerpt) not in normalized(passage):
        raise InputError("The passage does not match the selected source and location.")
    return excerpt


def medford_record(source_id):
    if source_id not in sources_by_id():
        raise InputError("Choose a source from the list.")
    record_path = MEDFORD / f"{source_id}.mfd"
    if not record_path.exists():
        raise InputError("The source MEDFORD record is missing. Run the project pipeline first.")
    record = record_path.read_text(encoding="utf-8")
    if not record.startswith("@MEDFORD ") or "@Data_Ref-URI " not in record:
        raise InputError("The source MEDFORD record is incomplete.")
    return record


def medford_source_metadata(source_id):
    record = medford_record(source_id)
    metadata = record.split("\n@Passage ", 1)[0].strip()
    return metadata


def check_claim(api_key, claim, excerpt, source_metadata):
    client = TypeSafeClient(api_key=api_key)
    response = client.system_one(
        state={
            "claim": claim,
            "cited_passage": excerpt,
            "medford_source_metadata": source_metadata,
        },
        questions={
            "supports_claim": Noul(
                instructions=(
                    "Does the cited passage directly support the claim? Use the MEDFORD source "
                    "metadata only to identify the author, title, date, and citation; do not treat "
                    "metadata as evidence for the claim's substantive content. Answer no if the "
                    "passage contradicts the claim, lacks the needed detail, or requires outside "
                    "information."
                )
            )
        },
    )
    score = response.model_dump(mode="json")["answers"]["supports_claim"]["noul"]
    if type(score) not in (int, float) or not 0 <= score <= 1:
        raise ValueError("JEV returned an invalid NouL value.")
    return score


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Do not log requests containing an API key or a claim.

    def send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def allowed_host(self):
        return self.headers.get("Host", "").split(":", 1)[0] in {"127.0.0.1", "localhost"}

    def do_GET(self):
        if not self.allowed_host():
            self.send_json(403, {"error": "Open this checker on localhost."})
            return
        request = urlsplit(self.path)
        if request.path == "/":
            self.send_bytes(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif request.path == "/api/sources":
            items = [public_source(source) for source in sources_by_id().values()]
            items.sort(key=lambda item: (item["date"] or "9999", item["title"]))
            self.send_json(200, {"sources": items})
        elif request.path == "/api/passage":
            query = parse_qs(request.query)
            try:
                info, location, passage = resolve_passage(
                    query.get("source_id", [""])[0], query.get("locator", [""])[0]
                )
                self.send_json(200, {"source": info, "location": location, "passage": passage})
            except InputError as exc:
                self.send_json(400, {"error": str(exc)})
        elif request.path == "/api/medford":
            query = parse_qs(request.query)
            try:
                source_id = query.get("source_id", [""])[0]
                self.send_json(200, {"source_id": source_id, "record": medford_record(source_id)})
            except InputError as exc:
                self.send_json(400, {"error": str(exc)})
        else:
            self.send_json(404, {"error": "Not found."})

    def do_POST(self):
        if not self.allowed_host():
            self.send_json(403, {"error": "Open this checker on localhost."})
            return
        if urlsplit(self.path).path != "/api/check":
            self.send_json(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 65536:
                raise InputError("Request is empty or too large.")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise InputError("Invalid request.")
            api_key = str(body.get("api_key") or "").strip()
            claim = str(body.get("claim") or "").strip()
            if not api_key:
                raise InputError("Enter your TypeSafe API key.")
            if not claim or len(claim) > MAX_CLAIM:
                raise InputError("Enter a claim of 1 to 1,000 characters.")
            info, location, passage = resolve_passage(body.get("source_id"), body.get("locator"))
            excerpt = validate_excerpt(body.get("excerpt"), passage)
            source_metadata = medford_source_metadata(info["id"])
        except (InputError, ValueError, TypeError) as exc:
            self.send_json(400, {"error": str(exc)})
            return

        try:
            score = check_claim(api_key, claim, excerpt, source_metadata)
        except Exception:
            self.send_json(502, {"error": "JEV could not score this claim. Check your key and connection, then try again."})
            return
        self.send_json(200, {
            "source": info,
            "location": location,
            "excerpt": excerpt,
            "noul": score,
            "support_percent": round(score * 100, 1),
        })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with HTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"Citation checker: http://127.0.0.1:{args.port}", flush=True)
        server.serve_forever()
