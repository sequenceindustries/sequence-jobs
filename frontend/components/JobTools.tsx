"use client";
import { useState } from "react";
import { api } from "@/lib/client";

// Interview practice (works without AI) and AI drafting (cover letter, CV suggestions; needs consent and AI enabled).
export function JobTools({ jobId }: { jobId: number }) {
  const [prep, setPrep] = useState<any>(null);
  const [q, setQ] = useState<string>(""); const [ans, setAns] = useState(""); const [fb, setFb] = useState<any>(null);
  const [consent, setConsent] = useState(false); const [disc, setDisc] = useState<string>("");
  const [out, setOut] = useState<any>(null); const [msg, setMsg] = useState<string | null>(null); const [busy, setBusy] = useState(false);

  async function loadPrep() {
    const r = await api("/api/interview/prep", "POST", { job_id: jobId });
    if (r.status === 401) { window.location.href = "/login"; return; }
    if (r.ok) { setPrep(r.data); setQ(r.data.questions[0]?.question ?? ""); } else setMsg(r.data?.message ?? "Could not load.");
  }
  async function feedback() {
    const r = await api("/api/interview/feedback", "POST", { question: q, answer: ans, job_id: jobId });
    if (r.ok) setFb(r.data); else setMsg(r.data?.message ?? "Could not review that answer.");
  }
  async function ai(kind: "cover" | "cv") {
    setBusy(true); setMsg(null); setOut(null);
    const cvs = await api("/api/cv");
    if (cvs.status === 401) { window.location.href = "/login"; return; }
    const cv = cvs.data?.cvs?.[0];
    if (!cv) { setBusy(false); setMsg("Upload a CV in your account first."); return; }
    const path = kind === "cover" ? "/api/cover-letter" : "/api/cv/improve";
    const r = await api(path, "POST", { job_id: jobId, cv_id: cv.id, ai_consent: consent, tone: "formal" });
    setBusy(false);
    if (r.status === 400 && r.data?.error === "consent_required") { setDisc(r.data.disclosure); setMsg("Please tick the consent box first."); return; }
    if (!r.ok) { setMsg(r.data?.message ?? "AI is not available right now."); return; }
    setOut({ kind, ...r.data });
  }
  async function download(text: string, format: "txt" | "docx") {
    const res = await fetch("/api/export", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": (await (await fetch("/api/auth/csrf")).json()).csrf_token }, body: JSON.stringify({ text, format }) });
    if (!res.ok) { setMsg("Could not export."); return; }
    const a = document.createElement("a"); a.href = URL.createObjectURL(await res.blob()); a.download = `cover-letter.${format}`; a.click();
  }

  return (
    <section aria-label="Prepare" className="card" style={{ marginTop: 16 }}>
      <h2 style={{ fontSize: "1.05rem", margin: "0 0 8px" }}>Prepare for this role</h2>
      <div className="chips"><button className="chip" onClick={loadPrep}>Interview practice</button></div>
      {prep && <div style={{ marginTop: 12 }}>
        <label className="hint" htmlFor="pq">Pick a question</label>
        <select id="pq" value={q} onChange={(e) => { setQ(e.target.value); setFb(null); }} style={{ width: "100%" }}>
          {prep.questions.map((x: any, i: number) => <option key={i}>{x.question}</option>)}</select>
        <label className="hint" htmlFor="pa">Your answer (practice only; not stored)</label>
        <textarea id="pa" rows={5} value={ans} onChange={(e) => setAns(e.target.value)} style={{ width: "100%" }} />
        <button className="chip" onClick={feedback} disabled={!ans.trim()}>Get feedback</button>
        {fb && <div><ul>{fb.what_worked.map((t: string) => <li key={t}>✓ {t}</li>)}{fb.to_improve.map((t: string) => <li key={t}>→ {t}</li>)}</ul><p className="hint">{fb.method}</p></div>}
        <details><summary>Questions to ask the employer</summary><ul>{prep.questions_to_ask_employer.map((t: string) => <li key={t}>{t}</li>)}</ul></details>
        <p className="hint">{prep.disclaimer}</p>
      </div>}
      <hr style={{ margin: "14px 0", border: 0, borderTop: "1px solid var(--border)" }} />
      <p className="hint">AI drafting: cover letter and CV suggestions. Drafts only; we never apply for you.</p>
      <label className="hint"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> I consent to my CV text (without contact details) being sent to our AI provider for this request.</label>
      {disc && <p className="hint">{disc}</p>}
      <div className="chips" style={{ marginTop: 8 }}>
        <button className="chip" disabled={busy} onClick={() => ai("cover")}>Draft cover letter</button>
        <button className="chip" disabled={busy} onClick={() => ai("cv")}>Suggest CV improvements</button></div>
      {msg && <p className="hint" role="status">{msg}</p>}
      {out?.kind === "cover" && (out.letter ? <div><p className="body" style={{ whiteSpace: "pre-wrap" }}>{out.letter}</p>
          <div className="chips"><button className="chip" onClick={() => download(out.letter, "docx")}>Download .docx</button><button className="chip" onClick={() => download(out.letter, "txt")}>Download .txt</button></div>
          <p className="hint">{out.note}</p></div>
        : <div className="error">{out.message}<ul>{out.problems?.map((p: string) => <li key={p}>{p}</li>)}</ul></div>)}
      {out?.kind === "cv" && <div>{out.suggestions.length === 0 && <p className="hint">No safe suggestions were produced.</p>}
        <ul>{out.suggestions.map((s: any) => <li key={s.id}><strong>{s.section}</strong>: <del>{s.original}</del> → {s.suggested}<br /><span className="hint">{s.rationale}</span></li>)}</ul>
        {out.rejected_for_unsupported_content.length > 0 && <p className="hint">{out.rejected_for_unsupported_content.length} suggestion(s) were hidden because they contained details not found in your CV.</p>}
        <p className="hint">{out.note}</p></div>}
    </section>
  );
}
