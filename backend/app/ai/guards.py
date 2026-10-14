"""Deterministic anti-fabrication guards for AI output about a person's own experience.

The model may reword and organise what the user provided. It must not add facts. `unsupported_claims` compares a piece
of generated text with the *support corpus* (the user's CV text, facts they typed, their profile skills) and returns
human-readable reasons when it finds a number, proper noun, qualification word or taxonomy skill that the corpus does
not support. The check is deliberately conservative: a false alarm costs the user a rejected suggestion; a miss would
put an invented claim on their CV.
"""
from __future__ import annotations

import re
from typing import Iterable

from ..services.skills import extract_skills

_QUAL_WORDS = ["certified", "certification", "degree", "diploma", "masters", "master's", "phd", "doctorate", "honours",
               "bachelor", "mba", "licensed", "accredited", "award", "awarded", "promoted", "managed a team", "led a team"]
_ALLOWED_CAPS = {"dear", "hiring", "manager", "team", "sincerely", "regards", "yours", "kind", "best", "thank", "thanks",
                 "faithfully", "i", "i'm", "i've", "i'd", "i'll", "south", "african", "africa", "cv", "mr", "ms", "mrs", "dr",
                 "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february", "march",
                 "april", "may", "june", "july", "august", "september", "october", "november", "december", "re", "to", "whom",
                 "it", "concern", "position", "role", "application", "attached", "resume", "curriculum", "vitae", "pty", "ltd",
                 "department", "human", "resources", "recruitment", "company", "organisation", "organization", "recruiter"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower())


def _num_key(tok: str) -> str:
    return re.sub(r"[\s,]", "", tok.lower()).rstrip(".")


def normalise_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def contains_verbatim(haystack: str, needle: str) -> bool:
    return bool(needle.strip()) and normalise_ws(needle) in normalise_ws(haystack)


def unsupported_claims(generated: str, support: Iterable[str], skill_support: Iterable[str] = ()) -> list[str]:
    """Reasons the text asserts something the support texts do not."""
    corpus = " \n ".join(support)
    corpus_low = _norm(corpus)
    corpus_nums = {_num_key(m) for m in re.findall(r"\d[\d\s,.]*\d%?|\d%?", corpus)}
    corpus_words = set(re.findall(r"[a-z][a-z'+#.-]*", corpus_low))
    reasons: list[str] = []

    for m in re.finditer(r"R?\s?\d[\d\s,.]*\d%?|R?\s?\d%?", generated):
        tok = m.group(0).strip()
        key = _num_key(tok.lstrip("Rr").strip())
        if key and key not in corpus_nums and _num_key(tok) not in corpus_nums:
            reasons.append(f"number not in your CV or facts: '{tok}'")

    # proper nouns: capitalised words that are not the first word of a sentence
    for sent in re.split(r"(?<=[.!?\n])\s+|\n", generated):
        words = re.findall(r"[A-Za-z][A-Za-z'&+#.-]*", sent)
        for i, w in enumerate(words):
            if i == 0 or not w[0].isupper() or len(w) < 3 or w.isupper() and len(w) <= 4 and w.lower() in corpus_words:
                continue
            lw = w.lower().strip(".'")
            if lw in _ALLOWED_CAPS or lw in corpus_words:
                continue
            reasons.append(f"name not in your CV or facts: '{w}'")

    for q in _QUAL_WORDS:
        if re.search(rf"\b{re.escape(q)}\b", generated, re.I) and not re.search(rf"\b{re.escape(q)}\b", corpus, re.I):
            reasons.append(f"qualification/achievement wording not in your CV or facts: '{q}'")

    supported_skills = set(extract_skills(corpus)) | {s.lower() for s in skill_support}
    for s in extract_skills(generated):
        if s not in supported_skills:
            reasons.append(f"skill not evidenced in your CV or facts: '{s}'")

    seen, out = set(), []
    for r in reasons:
        if r not in seen:
            seen.add(r); out.append(r)
    return out
