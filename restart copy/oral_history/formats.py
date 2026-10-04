"""Readers for Reddit JSON and time-coded video transcripts."""
import html
import json
import re

FORMATS = {"html", "wayback", "pdf", "txt", "markdown", "reddit", "vtt", "srt", "video"}
CAPTION_FORMATS = {"vtt", "srt", "video"}


def parse_captions(text):
    """Keep every cue and its original timing; do not invent missing speech."""
    cues = []
    timestamp = r"(?:\d{2,}:)?\d{2}:\d{2}[.,]\d{3}"
    timing = re.compile(rf"^({timestamp})\s+-->\s+({timestamp})(?:\s+.*)?$")

    def seconds(value):
        parts = value.replace(",", ".").split(":")
        hours, minutes, secs = (["0"] + parts if len(parts) == 2 else parts)
        if int(minutes) >= 60 or float(secs) >= 60:
            raise ValueError("Invalid caption timestamp.")
        return int(hours) * 3600 + int(minutes) * 60 + float(secs)

    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").lstrip("\ufeff")):
        lines = block.strip().splitlines()
        if not lines or lines[0].startswith(("NOTE", "STYLE", "REGION")):
            continue
        for index, line in enumerate(lines):
            match = timing.fullmatch(line.strip())
            if not match:
                continue
            start, end = map(seconds, match.groups())
            if end <= start:
                raise ValueError("Caption end must follow its start.")
            raw = " ".join(lines[index + 1:])
            voice = re.search(r"<v(?:\.[^ >]+)?\s+([^>]+)>", raw)
            clean = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
            if clean:
                cue = {"start_seconds": start, "end_seconds": end, "text": clean}
                if voice:
                    cue["speaker_label"] = html.unescape(voice.group(1))
                cues.append(cue)
            break
    if not cues:
        raise ValueError("No timed captions found; supply a valid VTT or SRT transcript.")
    return cues


def parse_reddit(payload):
    """Read a Reddit listing/comments response. Missing 'more' items stay explicit."""
    segments, warnings, seen = [], [], set()

    def walk(node):
        if isinstance(node, list):
            for child in node:
                walk(child)
            return
        if not isinstance(node, dict):
            return
        kind, data = node.get("kind"), node.get("data", {})
        if kind == "more":
            warnings.append("Reddit response omits additional comments (more placeholder).")
            return
        if kind in {"t1", "t3"}:
            name = data.get("name") or f"{kind}_{data.get('id', '')}"
            if name in seen:
                return
            seen.add(name)
            body = data.get("body", "") if kind == "t1" else data.get("selftext", "")
            if body and body not in {"[deleted]", "[removed]"}:
                permalink = data.get("permalink", "")
                segments.append({"reddit_id": name, "author": data.get("author", "[deleted]"),
                                 "text": html.unescape(body), "title": data.get("title", ""),
                                 "url": "https://www.reddit.com" + permalink if permalink.startswith("/") else permalink,
                                 "parent_id": data.get("parent_id"), "created_utc": data.get("created_utc")})
            walk(data.get("replies"))
        elif isinstance(data, dict):
            walk(data.get("children", []))

    walk(payload)
    if not segments:
        raise ValueError("No post/comment text in Reddit JSON; an error or link-only post is not a transcript.")
    warnings.append("Only supplied post/comment bodies are included; this is not a complete-thread guarantee.")
    return segments, list(dict.fromkeys(warnings))


def extract_structured(content, source_format):
    """Return text, segments, and warnings for the non-document formats."""
    if source_format == "reddit":
        segments, warnings = parse_reddit(json.loads(content.decode("utf-8-sig")))
        text = "\n\n".join(f"[{s['reddit_id']}] u/{s['author']}\n{s['text']}" for s in segments)
        return text, segments, warnings
    metadata = {}
    if source_format == "video":
        metadata = json.loads(content.decode("utf-8"))
        if metadata.get("caption_format") not in {"vtt", "srt"}:
            raise ValueError("Video cache must contain VTT or SRT captions.")
        text = metadata["captions"]
    else:
        text = content.decode("utf-8-sig")
    segments = parse_captions(text)
    warnings = []
    
    if metadata.get("caption_kind") == "automatic":
        warnings.append("These captions were automatically generated.")
    return "\n".join(s["text"] for s in segments), segments, warnings
