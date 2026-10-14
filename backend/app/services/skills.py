"""Deterministic skills taxonomy + job/CV requirement extraction.

Skills are found by explicit word-boundary matches only. This is a conservative extractor: it can miss
skills (so absence in a CV is 'not found', never proof of lacking a skill) but does not invent them.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# canonical name -> aliases (lowercase). Canonical name is also matched.
TAXONOMY: dict[str, list[str]] = {
    # tech
    "python": [], "java": [], "javascript": ["js"], "typescript": [], "c#": ["c sharp"], "c++": [],
    "php": [], "ruby": [], "golang": [], "sql": [], "postgresql": ["postgres"], "mysql": [],
    "mongodb": [], "redis": [], "flask": [], "django": [], "fastapi": [], "react": ["react.js", "reactjs"],
    "next.js": ["nextjs"], "node.js": ["nodejs", "node"], "html": [], "css": [], ".net": ["dotnet", "asp.net"],
    "aws": ["amazon web services"], "azure": [], "gcp": ["google cloud"], "docker": [], "kubernetes": ["k8s"],
    "git": ["github", "gitlab"], "linux": [], "rest api": ["rest apis", "restful"], "machine learning": [],
    "data analysis": ["data analytics"], "power bi": ["powerbi"], "tableau": [], "excel": ["microsoft excel", "ms excel"],
    "cybersecurity": ["information security"], "devops": [], "ci/cd": [], "software testing": ["qa", "test automation"],
    # design / marketing
    "photoshop": ["adobe photoshop"], "illustrator": ["adobe illustrator"], "indesign": ["adobe indesign"],
    "adobe creative suite": ["adobe creative cloud", "creative suite"], "figma": [], "graphic design": [],
    "ui design": ["ux design", "ui/ux"], "video editing": ["premiere pro", "after effects"],
    "social media": ["social media marketing"], "seo": ["search engine optimisation", "search engine optimization"],
    "content creation": ["content writing", "copywriting"], "digital marketing": [], "email marketing": [],
    "google analytics": [], "brand management": [], "campaign management": [],
    # finance / admin / ops
    "accounting": [], "bookkeeping": [], "financial reporting": ["financial statements"],
    "reconciliation": ["reconciliations", "bank reconciliation"], "payroll": [], "accounts payable": [],
    "accounts receivable": [], "budgeting": ["budgets"], "auditing": ["audit"], "vat": [], "tax": ["taxation"],
    "pastel": ["sage pastel"], "sage": [], "sap": [], "quickbooks": [], "xero": [],
    "ms office": ["microsoft office", "office 365", "ms word", "ms outlook", "microsoft word", "powerpoint"],
    "data capture": ["data capturing", "data entry"], "administration": ["administrative support"],
    "scheduling": ["diary management"], "procurement": ["purchasing"], "inventory management": ["stock control"],
    "supply chain": ["logistics"], "project management": ["pmp", "prince2"], "agile": ["scrum"],
    # people / service
    "customer service": ["customer support", "client service", "customer care"], "call centre": ["call center"],
    "sales": ["business development"], "negotiation": [], "communication": ["communication skills"],
    "teamwork": ["team player"], "leadership": ["team leadership", "people management"],
    "problem solving": ["problem-solving"], "time management": [], "report writing": [],
    "recruitment": ["talent acquisition"], "facilitation": [], "first aid": [],
    "drivers licence": ["code 8", "code 10", "code 14", "driver's license", "driver's licence", "driving licence"],
    "nursing": [], "teaching": ["lecturing"],
}

_ALIAS_TO_CANON: dict[str, str] = {}
for canon, aliases in TAXONOMY.items():
    _ALIAS_TO_CANON[canon] = canon
    for a in aliases:
        _ALIAS_TO_CANON[a] = canon


def _compile() -> re.Pattern:
    terms = sorted(_ALIAS_TO_CANON, key=len, reverse=True)
    body = "|".join(re.escape(t) for t in terms)
    # not preceded/followed by alphanumerics or tech punctuation that would make it part of a bigger token
    return re.compile(rf"(?<![A-Za-z0-9+#.]){'(?:' + body + ')'}(?![A-Za-z0-9+#])", re.IGNORECASE)


_PATTERN = _compile()
# Names that are also common words: count only when capitalised in the source text (SAP, Sage, Node).
_NEEDS_CAPITAL = {"sage", "sap", "node"}


def extract_skills(text: Optional[str]) -> list[str]:
    if not text:
        return []
    found: set[str] = set()
    for m in _PATTERN.finditer(text):
        raw = m.group(0)
        key = raw.lower()
        if key in _NEEDS_CAPITAL and not raw[0].isupper():
            continue
        found.add(_ALIAS_TO_CANON[key])
    return sorted(found)


# ---- experience / seniority / education (deterministic) --------------------------------------------------------
_YEARS_RANGE = re.compile(r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I)
_YEARS_MIN = re.compile(r"(?:at least|minimum(?: of)?|min\.?|over)?\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I)
_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_YEARS_WORD = re.compile(r"\b(" + "|".join(_NUM_WORDS) + r")\s*(?:\(\d+\))?\s*\+?\s*(?:years?|yrs?)", re.I)


def parse_min_experience_years(*texts: Optional[str]) -> Optional[int]:
    """Smallest explicit years figure that looks like a requirement. None if nothing stated."""
    blob = " ".join(t for t in texts if t)
    if not blob:
        return None
    m = _YEARS_RANGE.search(blob)
    if m:
        return min(int(m.group(1)), int(m.group(2)))
    vals = [int(x) for x in _YEARS_MIN.findall(blob) if 0 < int(x) <= 40]
    vals += [_NUM_WORDS[w.lower()] for w in _YEARS_WORD.findall(blob)]
    if re.search(r"\b(no experience (?:required|needed)|entry[- ]level)\b", blob, re.I) and not vals:
        return 0
    return min(vals) if vals else None


_SENIORITY = [
    ("entry", r"\b(intern(ship)?|graduate|trainee|learnership|entry[- ]level)\b"),
    ("junior", r"\bjunior\b"),
    ("senior", r"\b(senior|lead|principal|head of|manager|director|specialist iii)\b"),
]


def detect_seniority(title: Optional[str]) -> Optional[str]:
    t = title or ""
    for level, pat in _SENIORITY:
        if re.search(pat, t, re.I):
            return level
    return None


EDU_ORDER = ["matric", "certificate", "diploma", "degree", "honours", "masters"]
_EDU_PATTERNS = [
    ("masters", r"\b(master'?s|msc|mba|ma degree|m\.?com)\b"),
    ("honours", r"\b(honou?rs|bcom honou?rs|postgraduate)\b"),
    ("degree", r"\b(bachelor'?s?|b\.?sc|b\.?com|bcom|ba degree|b\.?tech|btech|degree|nqf (?:level )?7)\b"),
    ("diploma", r"\b(national diploma|advanced diploma|diploma|nqf (?:level )?6)\b"),
    ("certificate", r"\b(certificate|n[4-6]\b|nqf (?:level )?[45])"),
    ("matric", r"\b(matric|grade 12|nsc|senior certificate)\b"),
]


def detect_education(*texts: Optional[str]) -> Optional[str]:
    """Highest education level mentioned. For a job this is the requirement; for a CV, the attainment claim."""
    blob = " ".join(t for t in texts if t)
    for level, pat in _EDU_PATTERNS:           # ordered highest -> lowest
        if re.search(pat, blob, re.I):
            return level
    return None


def edu_rank(level: Optional[str]) -> Optional[int]:
    return EDU_ORDER.index(level) if level in EDU_ORDER else None
