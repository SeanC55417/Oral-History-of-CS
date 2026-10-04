from pathlib import Path

def clean(value):
    # Keep source text on one line so it cannot become a new MEDFORD tag.
    return " ".join(str(value).split())


def format_source(source):
    # Sets the source metadata tags, contributors, dates, and URL
    lines = [f"@MEDFORD {clean(source['title'])}", "@MEDFORD-Version 2.0", ""]
    contributors = []
    for author in source.get("authors", []):
        contributors.append((author, "Author"))
    
    if source.get("speaker"):
        if source.get("interviewer"):
            role = "Interviewee"
        else:
            role = "Speaker"
        contributors.append((source["speaker"], role))
    
    if source.get("interviewer"):
        contributors.append((source["interviewer"], "Interviewer"))
    
    for name, role in contributors:
        lines.extend([f"@Contributor {clean(name)}", f"@Contributor-Role {role}", ""])
    dates = []
    for interview_date in source.get("interview_dates", []):
        dates.append((interview_date, "Interview conducted"))
    
    if source.get("publication_date"):
        dates.append((source["publication_date"], "Published"))
    
    for date, note in dates:
        lines.extend([f"@Date {clean(date)}", f"@Date-Note {note}", ""])
    lines.extend([f"@Data_Ref {clean(source['title'])}",
                  f"@Data_Ref-Type {clean(source['format'])}",
                  f"@Data_Ref-URI {clean(source['url'])}",
                  f"@Data_Ref-Note Source ID: {source['id']}; kind: {clean(source.get('source_type', 'unspecified'))}"])
    
    return "\n".join(lines)

def format_passage(evidence, jev_record):
    # Sets quotation tags and attach the matching saved JEV answer
    if (evidence["source_id"] != jev_record["source_id"] or evidence["quote"] != jev_record["quote"]):
        raise ValueError("The JEV result belongs to different evidence.")

    cleaned_evidence = {}
    for field, value in evidence.items():
        if isinstance(value, str):
            cleaned_evidence[field] = clean(value)
        else:
            cleaned_evidence[field] = value
    evidence = cleaned_evidence
    response = jev_record["response"]
    answer = response["answers"]["describes_own_contribution"]

    score = answer["noul"]

    if type(score) not in (int, float) or not 0 <= score <= 1:
        raise ValueError("The JEV score must be a number between 0 and 1.")

    lines = [
        "@Passage P1",
        f"@Passage-SourceID {evidence['source_id']}",
        f"@Passage-Speaker {evidence['speaker']}",
        f"@Passage-Section {evidence['section']}",
        f"@Passage-Text {evidence['quote']}",
        f"@Passage-Context {evidence['context']}",
        f"@Passage-JevQuestion {jev_record['question']}",
        f"@Passage-JevModel {response['model']}",
        f"@Passage-JevNoul {score}",
        f"@Passage-JevMethod {jev_record['method']}",
    ]

    if "pdf_page" in evidence:
        lines.append(f"@Passage-PdfPage {evidence['pdf_page']}")
        if "pdf_page_end" in evidence:
            lines.append(f"@Passage-PdfPageEnd {evidence['pdf_page_end']}")

    return "\n".join(lines)

def write_record(source, evidence, jev_record, output_directory):
    if source["id"] != evidence["source_id"]:
        raise ValueError("The evidence belongs to a different source.")

    source_text = format_source(source)
    passage_text = format_passage(evidence, jev_record)

    record = source_text + "\n\n" + passage_text + "\n"

    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)

    file_path = directory / f"{source['id']}.mfd"
    file_path.write_text(record, encoding="utf-8")

    return file_path
