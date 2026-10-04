"""Process HTML and PDF sources in a straightforward loop."""
import argparse
import json
from pathlib import Path

from oral_history.sources import load_sources
from oral_history.retrieve import download_source, html_to_text, bitcointalk_post_to_text, x_post_to_text, pdf_to_text
from oral_history.extract import evaluate_evidence, question_for
from oral_history.medford import write_record
from oral_history.validate import validate_record

ROOT = Path(__file__).resolve().parent

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()

    selection.add_argument("--source", action="append", help="Process this ID; repeat for several")
    selection.add_argument("--all", action="store_true", help="Process every source (the default)")

    parser.add_argument("--evaluate", action="store_true", help="Evaluate missing or changed evidence but reuse matching saved results")
    parser.add_argument("--offline", action="store_true", help="Doesn't use any API calls")
    parser.add_argument("--extract-only", action="store_true", help="Stop after extracting source text")
    parser.add_argument("--refresh", action="store_true", help="Download source files again")
    parser.add_argument("--list", action="store_true", help="List source IDs")

    args = parser.parse_args(argv)
    if args.offline and (args.evaluate or args.refresh):
        parser.error("--offline cannot be combined with --evaluate or --refresh")

    # Loads the source list and quotations
    sources = load_sources(ROOT / "data/sources.json")
    if args.list:
        for source in sources:
            print(source["id"], source["format"], source["title"])
        return 0
    if args.source:
        known_ids = []
        for source in sources:
            known_ids.append(source["id"])

        unknown = []
        for requested_id in args.source:
            if requested_id not in known_ids and requested_id not in unknown:
                unknown.append(requested_id)
        if unknown:
            parser.error(f"Unknown source IDs: {', '.join(sorted(unknown))}")
        selected_sources = []
        for source in sources:
            if source["id"] in args.source:
                selected_sources.append(source)
        sources = selected_sources
        
    evidence_path = ROOT / "data/processed/evidence.json"
    evidence_records = json.loads(evidence_path.read_text(encoding="utf-8"))
    raw_directory = ROOT / "data/raw"
    processed_directory = ROOT / "data/processed"
    raw_directory.mkdir(parents=True, exist_ok=True)
    processed_directory.mkdir(parents=True, exist_ok=True)
    results = []

    for source in sources:
        source_id = source["id"]
        print(f"\n{source['title']} ({source['format']})")
        result = {"source_id": source_id}
        # Keep the same dictionary in the summary as its status changes below
        results.append(result)
        try:
            raw_path = raw_directory / f"{source_id}.{source['format']}"
            if args.refresh or not raw_path.exists():
                if args.offline:
                    raise ValueError(f"Offline mode: missing {raw_path.name}")
                raw_path.write_bytes(download_source(source))
            print("Source file:", raw_path.name)

            # Extracts text using either the HTML or PDF reader.
            pages = []
            if source["format"] == "html":
                if "message_id" in source:
                    text = bitcointalk_post_to_text(
                        raw_path.read_bytes(), source["message_id"], source["forum_author_id"]
                    )
                elif "x_post_id" in source:
                    text = x_post_to_text(
                        raw_path.read_bytes(), source["x_post_id"], source["x_author_handle"]
                    )
                else:
                    text = html_to_text(raw_path.read_bytes())
            else:
                text, pages = pdf_to_text(raw_path, source.get("pdf_extraction_mode", "plain"))
                page_records = []
                for page_number, page_text in enumerate(pages, start=1):
                    page_record = {"pdf_page": page_number, "text": page_text}
                    page_records.append(page_record)
                (processed_directory / f"{source_id}-pages.json").write_text(
                    json.dumps(page_records, indent=2, ensure_ascii=False), encoding="utf-8")
            if not text.strip():
                raise ValueError("No text extracted from this source.")
            (processed_directory / f"{source_id}.txt").write_text(text, encoding="utf-8")
            if args.extract_only:
                result["status"] = "extracted"
                print("Saved extracted text.")
                continue

            # Find the source's quote and check its wording and location.
            matches = []
            for item in evidence_records:
                if item["source_id"] == source_id:
                    matches.append(item)
            if not matches:
                result["status"] = "needs_evidence"
                print("Add a quotation for this source to evidence.json.")
                continue

            if len(matches) != 1:
                raise ValueError("Use one evidence record per source.")
            evidence = matches[0]
            if "message_id" in source and evidence.get("message_id") != source["message_id"]:
                raise ValueError("Evidence needs the source's Bitcointalk message ID.")
            if "x_post_id" in source and evidence.get("x_post_id") != source["x_post_id"]:
                raise ValueError("Evidence needs the source's X post ID.")

            if not evidence.get("speaker"):
                raise ValueError("Evidence needs a speaker or author.")
            
            if source.get("speaker") and source["speaker"] != evidence["speaker"]:
                raise ValueError("The evidence speaker does not match the source.")
            
            # Ignores line breaks and repeated spaces, but keep the original wording.
            quote = " ".join(evidence["quote"].split())
            if not quote or quote not in " ".join(text.split()):
                raise ValueError("The quotation does not match the source text.")
            
            if source["format"] == "pdf":
                first = evidence.get("pdf_page")
                last = evidence.get("pdf_page_end", first)
                if type(first) is not int or type(last) is not int or not 1 <= first <= last <= len(pages):
                    raise ValueError("Evidence needs valid PDF page numbers.")

                selected_pages = pages[first - 1:last]
                combined_page_text = " ".join(selected_pages)
                page_text = " ".join(combined_page_text.split())
                if quote not in page_text:
                    raise ValueError("The quotation does not match the specified PDF pages.")
            print("Quotation found:", evidence["speaker"])

            # A saved score is reusable only for the same source, speaker, quote, and question
            expected = {"source_id": source_id, "speaker": evidence["speaker"],
                        "quote": evidence["quote"], "question": question_for(evidence),
                        "method": "typesafe_api"}
            evaluation_path = processed_directory / f"{source_id}-jev.json"
            evaluation_record = None
            if evaluation_path.exists():
                saved = json.loads(evaluation_path.read_text(encoding="utf-8"))

                # Compare each expected field and stop at the first mismatch.
                saved_result_matches = True
                for key, expected_value in expected.items():
                    saved_value = saved.get(key)
                    if saved_value != expected_value:
                        saved_result_matches = False
                        break

                if saved_result_matches:
                    evaluation_record = saved

            if evaluation_record is not None:
                evaluation_origin = "saved"
            else:
                evaluation_origin = "new"

            if evaluation_record is None:
                # --evaluate calls the API for missing evaluations
                if not args.evaluate:
                    result["status"] = "needs_evaluation"
                    print("Run with --evaluate to request a JEV result.")
                    continue
                response = evaluate_evidence(evidence)
                evaluation_record = expected.copy()
                evaluation_record["response"] = response.model_dump(mode="json")
                evaluation_path.write_text(json.dumps(evaluation_record, indent=2), encoding="utf-8")

            score = evaluation_record["response"]["answers"]["describes_own_contribution"]["noul"]
            if type(score) not in (int, float) or not 0 <= score <= 1:
                raise ValueError("The JEV score must be a number between 0 and 1.")
            
            # Noul is a 0–1 answer to the question; multiply by 100 for display.
            result["jev_noul"] = score
            result["percent_true"] = round(score * 100, 2)
            result["evaluation_origin"] = evaluation_origin
            result["question"] = expected["question"]
            print(f"JEV: {score:.2%} true ({evaluation_origin} evaluation)")

            # Validate a temporary record before replacing the last successful export
            staged = write_record(source, evidence, evaluation_record, ROOT / "output/.staging")
            problems = validate_record(staged)
            
            if problems:
                staged.unlink(missing_ok=True)
                raise ValueError("\n".join(problems))
            final_path = ROOT / "output/medford" / staged.name
            final_path.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(final_path)
            result["status"] = "complete"
            result["record"] = str(final_path.relative_to(ROOT))
            print("Saved and validated:", final_path.name)
        except Exception as error:
            result["status"] = "error"
            result["error"] = str(error)
            print("Error:", error)

    # Replaces the summary each run so it describes only this run's selected sources.
    summary_path = ROOT / "output/run-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("\nResults: output/run-summary.json")
    
    for result in results:
        if result["status"] == "error":
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
