"""Explainable job recommendations for a profile (+ optional CV). Never keyword-only, never protected attributes.

Ranking score (0-100) = 0.60 * match score + 0.15 * preference fit + 0.15 * freshness + 0.10 * (closing-date sanity)
A job needs *some* evidence of relevance (a skill/role match) to be recommended at all.
Hard exclusions: dismissed jobs, closed/expired jobs, jobs whose stated closing date has passed,
and (when the user set a work-mode / province preference) jobs that explicitly contradict it.
Unknown values are never treated as contradictions.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from .matching import match_job
from .search import PUBLIC_FIELDS


def _freshness(published: Optional[date], today: date) -> Optional[float]:
    if published is None:
        return None
    age = (today - published).days
    return max(0.0, 1.0 - age / 45)          # linear decay over ~6 weeks


def recommend(conn, user_id: int, profile: dict, cv_text: Optional[str], cv_parsed: Optional[dict],
              include_dev: bool, limit: int = 20, today: Optional[date] = None) -> list[dict]:
    today = today or date.today()
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        f"SELECT {PUBLIC_FIELDS}, j.extracted_skills, j.min_experience_years, j.required_education "
        "FROM jobs j JOIN sources s ON s.id = j.source_id "
        "WHERE j.status = 'active' AND j.canonical_job_id IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM job_interactions i WHERE i.user_id = %s AND i.job_id = j.id AND i.state = 'dismissed') "
        + ("" if include_dev else "AND j.is_dev_data = false "),
        (user_id,)).fetchall()

    wm, provs, etypes = set(profile.get("work_modes", [])), set(profile.get("provinces", [])), set(profile.get("employment_types", []))
    out = []
    for j in rows:
        if j["closing_at"] and j["closing_at"] < now:
            continue
        reasons, pref_scores = [], []
        if wm and j["work_mode"] and j["work_mode"] not in wm:
            continue
        if provs and j["province"] and j["province"] not in provs and j["work_mode"] != "remote":
            continue
        if wm and j["work_mode"] in wm:
            reasons.append(f"work mode matches your preference ({j['work_mode']})"); pref_scores.append(1.0)
        if provs and j["province"] in provs:
            reasons.append(f"located in {j['province']}"); pref_scores.append(1.0)
        if etypes and j["employment_type"]:
            et = j["employment_type"].lower().replace(" ", "_").replace("-", "_")
            if et in etypes:
                reasons.append(f"employment type matches ({j['employment_type']})"); pref_scores.append(1.0)
            else:
                pref_scores.append(0.0)
        se = profile.get("salary_expectation")
        if se and j["salary_min"] is not None and j["salary_period"] == se["period"]:
            top = float(j["salary_max"] or j["salary_min"])
            if top >= se["min"]:
                reasons.append("stated salary meets your expectation"); pref_scores.append(1.0)
            else:
                pref_scores.append(0.0)

        m = match_job(j, cv_text, cv_parsed, profile)
        ev = m["skills_evidence"]
        role = next(c for c in m["components"] if c["name"] == "role")
        relevant = bool(ev["confirmed_in_cv"] or ev["stated_by_user"] or (role["score"] or 0) > 0 or
                        set(profile.get("categories", [])) & set(j["extracted_skills"]))
        if not relevant or m["overall_score"] is None:
            continue
        sk = ev["confirmed_in_cv"] + ev["stated_by_user"]
        if sk:
            reasons.insert(0, "skills match: " + ", ".join(sk))
        fresh = _freshness(j["published_at"], today)
        if fresh is not None and fresh > 0.7:
            reasons.append("recently posted")
        pref = sum(pref_scores) / len(pref_scores) if pref_scores else 0.5
        score = 0.60 * m["overall_score"] + 15 * pref + 15 * (fresh if fresh is not None else 0.4) + 10
        out.append({"job": {k: j[k] for k in j if k not in ("extracted_skills",)} | {"extracted_skills": j["extracted_skills"]},
                    "rank_score": round(score, 1), "match_score": m["overall_score"], "confidence": m["confidence"],
                    "reasons": reasons or ["relevant to your profile"], "missing_or_unverified": ev["not_found"]})
    out.sort(key=lambda r: r["rank_score"], reverse=True)
    return out[:limit]
