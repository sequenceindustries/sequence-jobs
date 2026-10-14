"use client";
import { useState } from "react";
import { api } from "@/lib/client";

// Save / track / match for a job. Logged-out users are sent to log in; nothing here blocks reading the job.
export function JobActions({ jobId, jobTitle }: { jobId: number; jobTitle: string }) {
  const [msg, setMsg] = useState<string | null>(null);
  const [match, setMatch] = useState<any>(null);

  async function act(path: string, method: string, body: unknown, ok: string) {
    const r = await api(path, method, body);
    if (r.status === 401) { window.location.href = "/login"; return null; }
    setMsg(r.ok ? ok : r.data?.message ?? r.data?.error ?? "Could not do that.");
    return r;
  }
  async function doMatch() {
    const cvs = await api("/api/cv");
    if (cvs.status === 401) { window.location.href = "/login"; return; }
    const first = cvs.data?.cvs?.[0];
    if (!first) { setMsg("Upload a CV in your account first, then check your match."); return; }
    const r = await api("/api/match", "POST", { job_id: jobId, cv_id: first.id });
    if (r.ok) { setMatch(r.data); setMsg(null); } else setMsg(r.data?.message ?? "Could not compute a match.");
  }

  return (
    <section aria-label="Your actions" className="card" style={{ marginTop: 16 }}>
      <div className="chips">
        <button className="chip" onClick={() => act(`/api/jobs/${jobId}/save`, "PUT", undefined, "Saved.")}>Save job</button>
        <button className="chip" onClick={() => act("/api/applications", "POST", { job_id: jobId, job_title: jobTitle, status: "interested" }, "Added to your tracker.")}>Track application</button>
        <button className="chip" onClick={doMatch}>Check my match</button>
      </div>
      {msg && <p className="hint" role="status">{msg}</p>}
      {match && (
        <div style={{ marginTop: 12 }}>
          <strong>{match.overall_score === null ? "Not enough information to score" : `Match: ${match.overall_score}/100`}</strong>{" "}
          <span className="tag">confidence: {match.confidence}</span>{match.confidence === "low" && <p className="hint">Low confidence: the advert or your CV has too little comparable detail, so treat this number as weak.</p>}
          <ul>{match.components?.map((c: any) => <li key={c.name}>{c.name}: {c.score === null ? "unknown" : Math.round(c.score * 100) + "%"}</li>)}</ul>
          {match.skills_evidence?.not_found?.length > 0 && <p className="hint">Not found in your CV (unverified, not necessarily a gap): {match.skills_evidence.not_found.join(", ")}</p>}
          <p className="hint">{match.disclaimer}</p>
        </div>
      )}
    </section>
  );
}
