"""CV ingestion: safe text extraction and conservative, deterministic parsing.

Safety: the raw upload is only ever read in memory and is never stored or executed. DOCX is read with zipfile
and regex (no XML parser, so no entity expansion); macro-enabled/legacy formats are rejected; zip bombs are capped.
PDF text is extracted with pdfminer (pure Python, no JavaScript execution), capped by pages and characters.

Nothing here invents content: it reports what the document says, plus clearly-labelled recommendations.
"""
from __future__ import annotations

import html
import io
import re
import zipfile
from datetime import date
from typing import Optional

from .skills import detect_education, extract_skills

ALLOWED_EXT = {"txt", "pdf", "docx"}
MAX_TEXT_CHARS = 60_000
MAX_PDF_PAGES = 20
MAX_DOCX_UNCOMPRESSED = 25 * 1024 * 1024


class CVError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)           # control characters
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_TEXT_CHARS]


def _docx_text(data: bytes) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise CVError("corrupt_file", "That file is not a valid .docx document.")
    infos = zf.infolist()
    if len(infos) > 2000 or sum(i.file_size for i in infos) > MAX_DOCX_UNCOMPRESSED:
        raise CVError("file_rejected", "The document is too large or complex to process.")
    names = {i.filename for i in infos}
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        raise CVError("macros_not_allowed", "Macro-enabled documents are not accepted. Save as a plain .docx or PDF.")
    if "word/document.xml" not in names:
        raise CVError("corrupt_file", "That file is not a valid .docx document.")
    xml = zf.read("word/document.xml")
    if len(xml) > 10 * 1024 * 1024:
        raise CVError("file_rejected", "The document is too large to process.")
    xml = xml.decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:(?:br|cr)\s*/>", "\n", xml)
    xml = re.sub(r"<w:tab\s*/>", "\t", xml)
    parts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>|(\n|\t)", xml)
    return html.unescape("".join(a or b for a, b in parts))


def _pdf_text(data: bytes) -> str:
    from pdfminer.high_level import extract_text
    try:
        return extract_text(io.BytesIO(data), maxpages=MAX_PDF_PAGES)
    except Exception:
        raise CVError("unreadable_pdf", "We could not read that PDF (it may be scanned, encrypted or damaged). "
                                        "Try a text-based PDF, a .docx, or paste your CV as text.")


def extract_text(filename: str, data: bytes, max_bytes: int = 2 * 1024 * 1024) -> tuple[str, str]:
    """Return (text, ext). Raises CVError with a user-safe message."""
    ext = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "")
    if ext not in ALLOWED_EXT:
        raise CVError("unsupported_type", "Upload a PDF, DOCX or plain text (.txt) file.")
    if not data:
        raise CVError("empty_file", "The file is empty.")
    if len(data) > max_bytes:
        raise CVError("file_too_large", f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
    # Content must match the claimed type (magic bytes), not just the extension.
    if ext == "pdf":
        if not data.startswith(b"%PDF-"):
            raise CVError("type_mismatch", "That file is not a real PDF.")
        text = _pdf_text(data)
    elif ext == "docx":
        if not data.startswith(b"PK\x03\x04"):
            raise CVError("type_mismatch", "That file is not a real .docx document.")
        text = _docx_text(data)
    else:
        if b"\x00" in data[:4096]:
            raise CVError("type_mismatch", "That file does not look like plain text.")
        text = data.decode("utf-8", errors="replace")
    text = _clean(text)
    if len(text) < 40:
        raise CVError("no_text", "We could not find readable text in that file.")
    return text, ext


# ---- parsing -----------------------------------------------------------------------------
SECTION_NAMES = {
    "experience": r"(work|professional|employment)?\s*(experience|history)|employment",
    "education": r"education|academic( background| qualifications)?|qualifications",
    "skills": r"(key |technical |core |professional )?skills|competenc(y|ies)",
    "certifications": r"certifications?|certificates?|courses|training",
    "achievements": r"achievements?|accomplishments?|awards?",
    "languages": r"languages?",
    "projects": r"projects?",
    "summary": r"(professional |career )?(summary|profile|objective)|about me",
    "references": r"references?",
}
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE = r"(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?(\d{4})"
_RANGE = re.compile(rf"{_DATE}\s*(?:-|–|—|to)\s*(?:{_DATE}|(present|current|now|date))", re.I)
_WEAK = re.compile(r"\b(responsible for|duties included|tasked with|worked on|helped with)\b", re.I)


def split_sections(text: str) -> dict[str, str]:
    lines = text.split("\n")
    sections: dict[str, list[str]] = {"_top": []}
    current = "_top"
    for line in lines:
        s = line.strip().strip(":").strip()
        key = None
        if 2 <= len(s) <= 40 and not re.search(r"[.!?]$", s):
            for name, pat in SECTION_NAMES.items():
                if re.fullmatch(pat, s, re.I):
                    key = name
                    break
        if key:
            current = key
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}


def _month_index(y: int, m: Optional[str]) -> int:
    return y * 12 + (_MONTHS.get((m or "jan")[:3].lower(), 1) - 1)


def parse_date_ranges(text: str, today: Optional[date] = None) -> list[tuple[int, int, bool]]:
    """[(start_month_idx, end_month_idx, open_ended)] using explicit ranges in the text only."""
    today = today or date.today()
    now_idx = today.year * 12 + today.month - 1
    out = []
    for m in _RANGE.finditer(text):
        sm, sy, em, ey, present = m.group(1), int(m.group(2)), m.group(3), m.group(4), m.group(5)
        start = _month_index(sy, sm)
        if present:
            end, open_end = now_idx, True
        else:
            end, open_end = _month_index(int(ey), em if em else "dec"), False
        out.append((start, end, open_end))
    return out


def estimate_years(ranges: list[tuple[int, int, bool]]) -> Optional[float]:
    """Union of explicit ranges (overlapping jobs are not double-counted). Estimate only."""
    valid = sorted((s, e) for s, e, _ in ranges if e >= s)
    if not valid:
        return None
    total, cur_s, cur_e = 0, valid[0][0], valid[0][1]
    for s, e in valid[1:]:
        if s <= cur_e + 1:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s + 1
            cur_s, cur_e = s, e
    total += cur_e - cur_s + 1
    return round(total / 12, 1)


def parse_cv(text: str, today: Optional[date] = None) -> dict:
    today = today or date.today()
    sections = split_sections(text)
    exp_text = sections.get("experience", "")
    edu_text = sections.get("education", "")
    words = len(text.split())
    ranges = parse_date_ranges(exp_text or text, today)
    now_idx = today.year * 12 + today.month - 1

    issues: list[dict] = []

    def issue(code, severity, message):
        issues.append({"code": code, "severity": severity, "message": message, "kind": "recommendation"})

    for needed, label in (("experience", "work experience"), ("education", "education"), ("skills", "skills")):
        if needed not in sections:
            issue(f"missing_{needed}_section", "info",
                  f"No clearly labelled {label} section was found. If you have it, add a heading so employers and "
                  f"automated systems can find it.")
    has_email = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text))
    has_phone = bool(re.search(r"(?:\+27|0)[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{4}", text))
    if not has_email:
        issue("no_email", "warning", "No email address was found.")
    if not has_phone:
        issue("no_phone", "info", "No South African phone number was found.")
    if words < 120:
        issue("very_short", "warning", "The CV is very short; add detail on duties and results.")
    if words > 1800:
        issue("very_long", "info", "The CV is long (over ~1,800 words); consider trimming to the most relevant roles.")

    # inconsistencies that need the USER to review (we never edit employment history)
    for s, e, open_end in ranges:
        if e < s:
            issue("date_order", "warning", "A date range ends before it starts; please check your dates.")
        if s > now_idx:
            issue("future_start", "warning", "A role starts in the future; please check your dates.")
    srt = sorted((s, e) for s, e, _ in ranges if e >= s)
    for (s1, e1), (s2, e2) in zip(srt, srt[1:]):
        if s2 - e1 > 12:
            issue("employment_gap", "info", f"There is a gap of about {(s2 - e1 - 1)} months between two roles; "
                                            "consider briefly explaining it if relevant.")
    weak = _WEAK.findall(exp_text or text)
    if len(weak) >= 3:
        issue("weak_phrasing", "info", "Several lines start with passive phrases like 'responsible for'. "
                                        "Lead with action verbs and results.")
    metrics = re.findall(r"\b\d+(?:[.,]\d+)?\s*%|\bR\s?\d[\d ,.]*\b|\b\d{2,}\+?\s+(?:clients|customers|staff|users|projects|accounts)\b", text)
    if exp_text and not metrics:
        issue("no_measurable_results", "info", "No measurable results (numbers, percentages, rand values) were found "
                                               "in your experience. Add them only where they are true.")

    stated = re.search(r"(\d{1,2})\+?\s*(?:years?|yrs?)(?:'?\s*(?:of)?\s*(?:relevant |work |professional )?experience)", text, re.I)
    langs = []
    if "languages" in sections:
        langs = [x.strip() for x in re.split(r"[,\n;•·|]", sections["languages"]) if 2 <= len(x.strip()) <= 30]

    sentences = [s for s in re.split(r"[.!?\n]+", text) if len(s.split()) >= 3]
    avg_sentence = round(sum(len(s.split()) for s in sentences) / len(sentences), 1) if sentences else None

    return {
        "sections_found": sorted(k for k in sections if k != "_top"),
        "skills": extract_skills(text),
        "education_level_claimed": detect_education(edu_text or text),
        "stated_years_experience": int(stated.group(1)) if stated else None,
        "estimated_years_from_dates": estimate_years(ranges),       # an ESTIMATE from explicit date ranges
        "certifications": [l.strip(" -•·*") for l in sections.get("certifications", "").split("\n") if l.strip()][:20],
        "languages": langs[:10],
        "has_email": has_email, "has_phone": has_phone,
        "stats": {"words": words, "avg_sentence_words": avg_sentence, "measurable_results": len(metrics)},
        "issues": issues,
        "note": "Extracted values come from your document. Issues are recommendations for you to review, "
                "not changes. Absence of a skill here does not mean you lack it.",
    }


def redact_contact(text: str) -> str:
    """Remove email addresses and phone numbers before text is sent to an AI provider (data minimisation)."""
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email removed]", text)
    text = re.sub(r"(?:\+?27|0)[\s-]?\(?\d{2}\)?[\s-]?\d{3}[\s-]?\d{4}", "[phone removed]", text)
    text = re.sub(r"\b\d{13}\b", "[number removed]", text)                 # SA ID-length numbers
    return text
