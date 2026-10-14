"""Deterministic job-to-CV matching.

METHODOLOGY (documented and tested; the AI model never computes or alters the score):

  overall = 100 * sum(weight_i * score_i) / sum(weight_i)   over components whose inputs are KNOWN

  component   weight  score_i
  skills       0.45   share of the job's extracted skills that the candidate evidences
                      (found in the CV text, or stated by the user in their profile)
  experience   0.25   min(candidate_years / job_min_years, 1); 1.0 if the job requires 0 / says entry level
  education    0.20   1.0 if candidate level >= required; 0.5 if exactly one level below; else 0.0
  role         0.10   share of the job-title keywords that appear in the CV text

A component with unknown input (job states no skills; CV gives no years; etc.) is EXCLUDED and the remaining
weights are re-normalised, so missing information is never treated as a mismatch. `coverage` reports the share of the
total weight that could be assessed, and a low coverage lowers `confidence` (low < 0.5 <= medium < 0.8 <= high).

Evidence classes per job skill:
  confirmed_in_cv     the skill appears in the CV text
  stated_by_user      the user listed it in their profile (not verified against the CV)
  not_found           in neither -> "missing or unverified", NOT proof the candidate lacks it
  confirmed_gap       the user explicitly said they do not have it (profile.skills_absent)

This score is decision support. It is not a probability of being hired or an assessment of employability.
"""
from __future__ import annotations

import re
from typing import Optional

from .skills import EDU_ORDER, edu_rank, extract_skills

WEIGHTS = {"skills": 0.45, "experience": 0.25, "education": 0.20, "role": 0.10}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

DISCLAIMER = ("This match score compares what your CV and profile say with what the advert states. It is decision "
              "support only: it does not predict whether you will be shortlisted or hired, and employers weigh "
              "factors this platform cannot see.")

_STOP = {"and", "or", "the", "a", "an", "of", "for", "to", "in", "at", "with", "senior", "junior", "assistant",
         "officer", "specialist", "remote", "part", "time", "full", "contract", "intern", "internship"}


def _title_keywords(title: str) -> list[str]:
    return [w for w in re.findall(r"[a-z][a-z+#.]{2,}", (title or "").lower()) if w not in _STOP]


def match_job(job: dict, cv_text: Optional[str], cv_parsed: Optional[dict], profile: Optional[dict] = None) -> dict:
    profile = profile or {}
    cv_text = cv_text or ""
    cv_low = cv_text.lower()
    parsed = cv_parsed or {}

    job_skills = list(job.get("extracted_skills") or [])
    cv_skills = set(parsed.get("skills") or extract_skills(cv_text))
    stated = {s.lower() for s in profile.get("skills", [])}
    absent = {s.lower() for s in profile.get("skills_absent", [])}

    evidence = {"confirmed_in_cv": [], "stated_by_user": [], "not_found": [], "confirmed_gap": []}
    for s in job_skills:
        if s in cv_skills:
            evidence["confirmed_in_cv"].append(s)
        elif s in stated:
            evidence["stated_by_user"].append(s)
        elif s in absent:
            evidence["confirmed_gap"].append(s)
        else:
            evidence["not_found"].append(s)

    components = []

    # skills
    if job_skills:
        got = len(evidence["confirmed_in_cv"]) + len(evidence["stated_by_user"])
        components.append(("skills", got / len(job_skills), f"{got} of {len(job_skills)} skills in the advert are evidenced"))
    else:
        components.append(("skills", None, "The advert lists no skills we could identify"))

    # experience
    need = job.get("min_experience_years")
    have = profile.get("years_experience")
    have_src = "your profile"
    if have is None:
        have = parsed.get("stated_years_experience")
        have_src = "your CV (stated)"
    if have is None:
        have = parsed.get("estimated_years_from_dates")
        have_src = "your CV (estimated from dates)"
    if need is None:
        components.append(("experience", None, "The advert states no experience requirement"))
    elif need == 0:
        components.append(("experience", 1.0, "No experience required"))
    elif have is None:
        components.append(("experience", None, f"The advert asks for {need}+ years; your years of experience are unknown"))
    else:
        components.append(("experience", min(have / need, 1.0), f"Advert asks {need}+ years; {have} year(s) from {have_src}"))

    # education
    req = edu_rank(job.get("required_education"))
    claimed = edu_rank(parsed.get("education_level_claimed"))
    prof_levels = [edu_rank(q) for q in profile.get("qualifications", []) if edu_rank(q) is not None]
    if prof_levels:
        claimed = max(prof_levels + ([claimed] if claimed is not None else []))
    if req is None:
        components.append(("education", None, "The advert states no minimum qualification we could identify"))
    elif claimed is None:
        components.append(("education", None, f"Advert asks for {job['required_education']}; your qualification level is not stated"))
    else:
        diff = claimed - req
        score = 1.0 if diff >= 0 else 0.5 if diff == -1 else 0.0
        components.append(("education", score, f"Advert asks for {EDU_ORDER[req]}; you state {EDU_ORDER[claimed]}"))

    # role alignment
    kws = _title_keywords(job.get("title", ""))
    if kws and cv_low:
        hit = [k for k in kws if k in cv_low]
        components.append(("role", len(hit) / len(kws), f"{len(hit)} of {len(kws)} job-title keywords appear in your CV"))
    else:
        components.append(("role", None, "Not enough information to compare the role title"))

    known = [(n, s, why) for n, s, why in components if s is not None]
    wsum = sum(WEIGHTS[n] for n, _, _ in known)
    overall = round(100 * sum(WEIGHTS[n] * s for n, s, _ in known) / wsum) if wsum else None
    coverage = round(wsum, 2)
    confidence = "high" if coverage >= 0.8 else "medium" if coverage >= 0.5 else "low"

    questions = []
    if evidence["not_found"]:
        questions.append("Do you have experience with: " + ", ".join(evidence["not_found"]) +
                         "? If so, add it to your CV where it is true.")
    if need and have is None:
        questions.append(f"The advert asks for {need}+ years of experience. How many relevant years do you have?")
    if job.get("closing_at") is None:
        questions.append("No closing date was stated; check the original advert before applying.")

    return {
        "overall_score": overall,
        "confidence": confidence,
        "coverage": coverage,
        "weights": WEIGHTS,
        "components": [{"name": n, "weight": WEIGHTS[n], "score": None if s is None else round(s, 2),
                        "assessed": s is not None, "explanation": why} for n, s, why in components],
        "skills_evidence": evidence,
        "relevant_keywords": sorted(set(job_skills) | set(_title_keywords(job.get("title", "")))),
        "weaknesses": [f"Not evidenced: {s}" for s in evidence["not_found"]] +
                      [f"You told us you do not have: {s}" for s in evidence["confirmed_gap"]],
        "questions_before_applying": questions,
        "disclaimer": DISCLAIMER,
    }
