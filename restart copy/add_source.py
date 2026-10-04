"""Add a curated source without editing the catalog by hand."""
import argparse
import json
from pathlib import Path
from oral_history.formats import FORMATS
from oral_history.sources import load_sources, validate_source

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("id", "title", "url"):
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--format", required=True, choices=sorted(FORMATS))
    for field in ("speaker", "source-type", "publisher", "local-path", "download-url",
                  "transcript-url", "transcript-format", "content-selector", "language", "publication-date"):
        parser.add_argument("--" + field)
    parser.add_argument("--author", action="append", help="Repeat for multiple authors")
    parser.add_argument("--allow-auto-captions", action="store_true")
    args = vars(parser.parse_args())
    source = {k: v for k, v in args.items() if v is not None and v is not False}
    if "author" in source:
        source["authors"] = source.pop("author")
    validate_source(source)
    path = ROOT / "data/sources.json"
    sources = load_sources(path)
    if any(s["id"] == source["id"] for s in sources):
        parser.error("Source ID already exists; edit its existing catalog entry.")
    sources.append(source)
    path.write_text(json.dumps(sources, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Added {source['id']}. Next: python main.py --source {source['id']} --extract-only")


if __name__ == "__main__":
    main()
