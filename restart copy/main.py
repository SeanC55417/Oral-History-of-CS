"""Run one source or the whole catalog. API calls require --evaluate."""
import argparse
import json
from pathlib import Path

from oral_history.pipeline import process_source, save_json
from oral_history.sources import load_sources

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--source", action="append", help="Source ID; repeat to select several")
    group.add_argument("--all", action="store_true", help="Process every catalog source")
    parser.add_argument("--list", action="store_true", help="List available sources")
    parser.add_argument("--extract-only", action="store_true", help="Save text without evaluating or exporting")
    parser.add_argument("--offline", action="store_true", help="Use saved raw files and JEV results only")
    parser.add_argument("--refresh", action="store_true", help="Fetch raw sources again")
    parser.add_argument("--evaluate", action="store_true", help="Call JEV for missing or changed evaluations")
    args = parser.parse_args(argv)
    if args.offline and (args.refresh or args.evaluate):
        parser.error("--offline cannot be combined with --refresh or --evaluate")
    sources = load_sources(ROOT / "data/sources.json")
    if args.list:
        for s in sources:
            print(f"{s['id']:24} {s['format']:4} {s.get('speaker') or s['title']}")
        return 0
    ids = args.source or ["ieee-liskov-1991"]
    unknown = set(ids) - {s["id"] for s in sources}
    if unknown and not args.all:
        parser.error(f"Unknown source IDs: {', '.join(sorted(unknown))}")
    selected = sources if args.all else [s for s in sources if s["id"] in ids]
    evidence_path = ROOT / "data/processed/evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else []
    results = []
    for source in selected:
        print(f"\n{source['title']} ({source['format']})")
        try:
            result = process_source(source, evidence, ROOT, offline=args.offline,
                                    refresh=args.refresh, extract_only=args.extract_only,
                                    evaluate=args.evaluate)
        except Exception as exc:
            # Keep a failed source from preventing the rest of a batch from running.
            result = {"source_id": source["id"], "status": "error", "error": str(exc)}
        results.append(result)
        print(result["status"])
        for warning in result.get("warnings", []):
            print("Note:", warning)
        if "error" in result:
            print(result["error"])
        if "record" in result:
            print("Validated record:", result["record"])
        if "next_step" in result:
            print("Next:", result["next_step"])
    save_json(ROOT / "output/run-summary.json", results)
    print("\nRun details: output/run-summary.json")
    return int(any(r["status"] == "error" for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
