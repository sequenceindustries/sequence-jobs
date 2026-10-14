"""AI-gated and AI-optional endpoints. AI calls need explicit consent, are rate limited per user, and answer 503
(`ai_unavailable`) when AI is not configured / over budget / fails validation. Nothing is ever fabricated as a fallback."""
from __future__ import annotations

import io

from flask import Blueprint, current_app, jsonify, request, send_file

from .ai import workflows as wf
from .ai.provider import AIOutputInvalid, AIUnavailable
from .api_user import _include_dev, _job_for_match, _json, _own_cv, _profile, _uid
from .auth import db_url, limited, login_required
from .db import connect
from .services.search import search_jobs

bp = Blueprint("ai", __name__)


def _consent_missing():
    if _json().get("ai_consent") is not True:
        return jsonify(error="consent_required", message="Tick the consent box to use this AI feature.",
                       disclosure=wf.DISCLOSURE), 400
    return None


def _unavailable(e):
    if isinstance(e, AIOutputInvalid):
        return jsonify(error="ai_output_invalid", message="The AI returned an unusable answer. Nothing was changed; try again."), 502
    return jsonify(error="ai_unavailable", message="AI features are not available right now. The rest of the site works normally."), 503


def _load(c, body, need_cv=True):
    try:
        job = _job_for_match(c, int(body.get("job_id")))
    except (TypeError, ValueError):
        return None, None, (jsonify(error="invalid", message="job_id is required."), 400)
    if not job:
        return None, None, (jsonify(error="job_not_found"), 404)
    cv = None
    if need_cv or body.get("cv_id") is not None:
        try:
            cv = _own_cv(c, int(body.get("cv_id")))
        except (TypeError, ValueError):
            cv = None
        if not cv:
            return None, None, (jsonify(error="cv_not_found"), 404)
    return job, cv, None


def _facts(body) -> str:
    f = body.get("facts")
    return f[:2000] if isinstance(f, str) else ""


@bp.get("/ai/disclosure")
def disclosure():
    gw = current_app.config["AI"]
    from .ai.provider import NullProvider
    return jsonify(disclosure=wf.DISCLOSURE, ai_available=not isinstance(gw.provider, NullProvider) and gw.daily_budget_usd > 0)


@bp.post("/cv/improve")
@login_required
@limited("ai", 30, 3600, by_user=True)
def cv_improve():
    if (r := _consent_missing()): return r
    body = _json()
    with connect(db_url()) as c:
        job, cv, err = _load(c, body)
    if err: return err
    try:
        return jsonify(wf.improve_cv(current_app.config["AI"], cv["text_content"], job, _facts(body)))
    except (AIUnavailable, AIOutputInvalid) as e:
        return _unavailable(e)


@bp.post("/cv/improve/apply")
@login_required
def cv_apply():
    """No AI: applies only suggestions the user approved. Returns the new text; the stored CV is unchanged unless save=true."""
    body = _json()
    with connect(db_url()) as c:
        cv = _own_cv(c, int(body["cv_id"])) if str(body.get("cv_id", "")).isdigit() else None
        if not cv: return jsonify(error="cv_not_found"), 404
        approved = body.get("approved")
        if not isinstance(approved, list): return jsonify(error="invalid", message="approved must be a list."), 400
        res = wf.apply_suggestions(cv["text_content"], approved[:30])
        if body.get("save") is True and res["applied"]:
            from .services.cv import parse_cv
            n = c.execute("SELECT count(*) n FROM cvs WHERE user_id=%s", (_uid(),)).fetchone()["n"]
            if n >= 5: return jsonify(error="cv_limit", message="Delete a CV first (max 5)."), 400
            from psycopg.types.json import Jsonb
            row = c.execute("INSERT INTO cvs (user_id,label,source_ext,text_content,parsed,expires_at) "
                            "VALUES (%s,%s,'txt',%s,%s,%s) RETURNING id",
                            (_uid(), (cv["label"] or "CV") + " (edited)", res["text"], Jsonb(parse_cv(res["text"])), cv["expires_at"])).fetchone()
            c.commit(); res["saved_as_cv_id"] = row["id"]
    return jsonify(res)


@bp.post("/cover-letter")
@login_required
@limited("ai", 30, 3600, by_user=True)
def cover_letter():
    if (r := _consent_missing()): return r
    body = _json()
    if body.get("tone", "formal") not in wf.TONES:
        return jsonify(error="invalid", message="tone must be one of " + ", ".join(wf.TONES)), 400
    with connect(db_url()) as c:
        job, cv, err = _load(c, body)
        prof = _profile(c)
    if err: return err
    try:
        return jsonify(wf.cover_letter(current_app.config["AI"], cv["text_content"], job, body.get("tone", "formal"),
                                       str(body.get("candidate_name") or "")[:80], _facts(body), prof.get("skills", [])))
    except (AIUnavailable, AIOutputInvalid) as e:
        return _unavailable(e)


@bp.post("/interview/prep")
@login_required
def interview_prep():
    """Template prep always works. AI questions are added only with consent and only when AI is available."""
    body = _json()
    with connect(db_url()) as c:
        job, _, err = _load(c, body, need_cv=False)
    if err: return err
    out = wf.interview_baseline(job)
    out["ai"] = {"requested": bool(body.get("use_ai")), "added": False}
    if body.get("use_ai"):
        if body.get("ai_consent") is not True:
            return _consent_missing()
        try:
            extra = wf.interview_ai(current_app.config["AI"], job)
            out["questions"] += extra["questions"]
            out["practice_scenarios"] += extra["practice_scenarios"]
            out["questions_to_ask_employer"] += extra["questions_to_ask_employer"]
            out["ai"]["added"] = True
        except (AIUnavailable, AIOutputInvalid):
            out["ai"]["note"] = "AI questions are unavailable; showing template questions only."
    return jsonify(out)


@bp.post("/interview/feedback")
@login_required
@limited("feedback", 120, 3600, by_user=True)
def interview_feedback():
    body = _json()
    q, a = body.get("question"), body.get("answer")
    if not (isinstance(q, str) and isinstance(a, str) and q.strip() and a.strip()) or len(a) > 5000:
        return jsonify(error="invalid", message="question and answer (max 5000 chars) are required."), 400
    job = None
    if body.get("job_id") is not None:
        with connect(db_url()) as c:
            job, _, err = _load(c, body, need_cv=False)
        if err: return err
    return jsonify(wf.interview_feedback(q, a, job))


@bp.post("/assistant/chat")
@login_required
@limited("ai", 30, 3600, by_user=True)
def assistant_chat():
    body = _json()
    msg = body.get("message")
    if not isinstance(msg, str) or not msg.strip() or len(msg) > 500:
        return jsonify(error="invalid", message="message (max 500 chars) is required."), 400
    with connect(db_url()) as c:
        found = search_jobs(c, q=msg, filters={}, page=1, per_page=8, include_dev=_include_dev())["results"]
        prof = _profile(c)
        cv = _own_cv(c, int(body["cv_id"])) if str(body.get("cv_id", "")).isdigit() else None
    fallback = {"from_listings_search": [{"id": j["id"], "title": j["title"], "employer": j["employer"]} for j in found]}
    if body.get("ai_consent") is not True:
        return jsonify(error="consent_required", message="Tick the consent box to use the AI assistant.",
                       disclosure=wf.DISCLOSURE, **fallback), 400
    full = []
    with connect(db_url()) as c:
        for j in found:
            full.append(_job_for_match(c, j["id"]) or j)
    try:
        out = wf.assistant_answer(current_app.config["AI"], msg, full, cv["parsed"] if cv else None, prof)
        out["related_listings"] = fallback["from_listings_search"]
        return jsonify(out)
    except (AIUnavailable, AIOutputInvalid) as e:
        resp, code = _unavailable(e)
        data = resp.get_json(); data.update(fallback)
        return jsonify(data), code


@bp.post("/export")
@login_required
def export():
    body = _json()
    text, fmt = body.get("text"), body.get("format", "txt")
    if not isinstance(text, str) or not text.strip() or len(text) > 30000 or fmt not in ("txt", "docx"):
        return jsonify(error="invalid", message="text (max 30000 chars) and format txt|docx are required."), 400
    name = "document." + fmt
    if fmt == "txt":
        return send_file(io.BytesIO(text.encode()), mimetype="text/plain", as_attachment=True, download_name=name)
    from docx import Document
    d = Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    buf = io.BytesIO(); d.save(buf); buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     as_attachment=True, download_name=name)
