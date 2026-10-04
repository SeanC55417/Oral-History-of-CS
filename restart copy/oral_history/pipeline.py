"""Small shared pipeline used by the CLI and offline exporter."""
import hashlib
import json
from datetime import datetime, timezone

from .extract import QUESTION, evaluate_evidence, question_for
from .medford import write_record
from .retrieve import obtain_content, extract_document, archive_details
from .formats import CAPTION_FORMATS
import math
from .validate import validate_record


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize(text):
    return " ".join(text.split())


def check_evidence(source, evidence, text, pages, segments=None):
    if evidence["source_id"] != source["id"]:
        raise ValueError("Evidence source does not match the catalog.")
    
    if source.get("speaker") and evidence["speaker"] != source["speaker"]:
        raise ValueError("Evidence speaker does not match the catalog.")
    
    if not evidence.get("speaker", "").strip():
        raise ValueError("Evidence needs the actual speaker/author, not just the subject.")
    quote = normalize(evidence["quote"])
    
    if not quote or quote not in normalize(text):
        raise ValueError("The quotation does not match the extracted source text.")
    
    if source["format"] == "pdf":
        number = evidence.get("pdf_page")
        end = evidence.get("pdf_page_end", number)
        
        if type(number) is not int or type(end) is not int or not 1 <= number <= end <= len(pages):
            raise ValueError("PDF evidence needs a valid pdf_page (and optional pdf_page_end).")
        selected = "\n\n".join(p["text"] for p in pages[number - 1:end])
        
        if quote not in normalize(selected):
            raise ValueError("Quotation does not occur on the recorded PDF page(s).")

    if source["format"] == "reddit":
        selected = [s for s in (segments or []) if s["reddit_id"] == evidence.get("reddit_id")]
        
        if len(selected) != 1 or quote not in normalize(selected[0]["text"]):
            raise ValueError("Quote must match the supplied reddit_id body.")
        
        if evidence["speaker"].removeprefix("u/") != selected[0]["author"]:
            raise ValueError("Reddit quotation author does not match the selected comment.")
    
    if source["format"] in CAPTION_FORMATS:
        start, end = evidence.get("start_seconds"), evidence.get("end_seconds")
        
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end):
            raise ValueError("Caption evidence needs valid start_seconds and end_seconds.")
        selected = [s for s in (segments or []) if s["start_seconds"] >= start and s["end_seconds"] <= end]
        
        if not selected or quote not in normalize(" ".join(s["text"] for s in selected)):
            raise ValueError("Quotation must match cues contained in the selected timestamp range.")


def cache_matches(record, evidence):
    return (record.get("source_id") == evidence["source_id"]
            and record.get("speaker") == evidence["speaker"]
            and record.get("quote") == evidence["quote"]
            and record.get("question") == question_for(evidence)
            and record.get("method") == "typesafe_api")


def process_source(source, evidence_records, root, *, offline=False, refresh=False, extract_only=False, evaluate=False):
    
    if offline and (refresh or evaluate):
        raise ValueError("Offline mode cannot refresh sources or call JEV.")
    
    source_id = source["id"]
    processed = root / "data/processed"
    content, raw_path = obtain_content(source, root, offline, refresh)
    document = extract_document(content, source)
    text, pages = document["text"], document["pages"]
    segments = document["segments"]
    processed.mkdir(parents=True, exist_ok=True)
    (processed / f"{source_id}.txt").write_text(text, encoding="utf-8")
    
    if pages:
        save_json(processed / f"{source_id}-pages.json", pages)
    if segments:
        save_json(processed / f"{source_id}-segments.json", segments)
    provenance = {
        "source_id": source_id, "url": source["url"], "format": source["format"],
        "selection_method": "curated_catalog", "raw_file": str(raw_path.relative_to(root)),
        "sha256": hashlib.sha256(content).hexdigest(),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "empty_pdf_pages": [p["pdf_page"] for p in pages if not p["text"].strip()],
    }
    retrieval_path = raw_path.with_name(raw_path.name + ".retrieval.json")
    if retrieval_path.exists():
        provenance["retrieval"] = json.loads(retrieval_path.read_text(encoding="utf-8"))
    
    if source["format"] == "wayback":
        provenance["requested_archive"] = archive_details(source["url"])
    provenance["extraction_options"] = {k: source[k] for k in ("pdf_extraction_mode", "content_selector") if k in source}
    provenance["warnings"] = document["warnings"]
    browser_path = processed / "browser-result.json"
    
    if browser_path.exists():
        browser = json.loads(browser_path.read_text(encoding="utf-8"))
        
        if (browser.get("verified") is True and browser.get("source_id") == source_id
                and browser.get("url") == source["url"]):
            provenance["selection_method"] = "jev_guided_browser_navigation"
            provenance["browser_result"] = browser
    save_json(processed / f"{source_id}-provenance.json", provenance)
    result = {"source_id": source_id, "format": source["format"],
              "characters": len(text), "pdf_pages": len(pages),
              "selection_method": provenance["selection_method"], "warnings": document["warnings"]}
    
    if extract_only:
        return dict(result, status="extracted")
    matches = [e for e in evidence_records if e["source_id"] == source_id]
    
    if not matches:
        return dict(result, status="needs_evidence")
    
    if len(matches) != 1:
        raise ValueError("This MVP supports one passage per source.")
    
    evidence = matches[0]
    check_evidence(source, evidence, text, pages, segments)
    cache_path = processed / f"{source_id}-jev.json"
    record = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else None
    
    if record is None or not cache_matches(record, evidence):
        if not evaluate:
            return dict(result, status="needs_evaluation",
                        next_step=f"python main.py --source {source_id} --evaluate")
        response = evaluate_evidence(evidence)
        record = {"source_id": source_id, "speaker": evidence["speaker"],
                  "quote": evidence["quote"], "question": question_for(evidence), "method": "typesafe_api",
                  "response": response.model_dump(mode="json")}
        save_json(cache_path, record)
    
    # Validate in a staging directory; never overwrite a good final record with a failed export.
    staged = write_record(source, evidence, record, root / "output/.staging")
    problems = validate_record(staged)
    if problems:
        staged.unlink(missing_ok=True)
        raise ValueError("\n".join(problems))
    
    final = root / "output/medford" / staged.name
    final.parent.mkdir(parents=True, exist_ok=True)
    staged.replace(final)
    return dict(result, status="complete", record=str(final.relative_to(root)),
                jev_score=record["response"]["answers"]["describes_own_contribution"]["noul"])
