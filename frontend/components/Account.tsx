"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, uploadCv } from "@/lib/client";

const STATUSES = ["interested", "preparing", "applied", "interview", "assessment", "offer", "rejected", "withdrawn", "closed"];
type Tab = "recommendations" | "saved" | "applications" | "alerts" | "cv" | "profile";
const TABS: [Tab, string][] = [["recommendations", "For you"], ["saved", "Saved"], ["applications", "Applications"],
  ["alerts", "Alerts"], ["cv", "My CVs"], ["profile", "Profile"]];

export function Account() {
  const [me, setMe] = useState<any>(undefined);
  const [tab, setTab] = useState<Tab>("recommendations");

  useEffect(() => { api("/api/auth/me").then((r) => setMe(r.ok ? r.data.user : null)); }, []);
  useEffect(() => { if (me === null) window.location.href = "/login"; }, [me]);
  if (!me) return <p className="hint">Loading…</p>;

  async function logout() { await api("/api/auth/logout", "POST"); window.location.href = "/"; }
  async function del() {
    if (!confirm("Permanently delete your account and all your data?")) return;
    const r = await api("/api/auth/account", "DELETE");
    if (r.ok) window.location.href = "/";
  }

  return (
    <div className="section">
      <h1 style={{ fontSize: "1.5rem" }}>Your account</h1>
      <p className="hint">{me.email} · <button className="chip" onClick={logout}>Log out</button></p>
      <div className="chips" role="tablist" style={{ margin: "12px 0" }}>
        {TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className="chip" style={tab === k ? { borderColor: "var(--brand)" } : undefined} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === "recommendations" && <Recs />}
      {tab === "saved" && <Saved />}
      {tab === "applications" && <Apps />}
      {tab === "alerts" && <Alerts />}
      {tab === "cv" && <Cvs />}
      {tab === "profile" && <Profile />}
      <p className="hint" style={{ marginTop: 32 }}><button className="chip" onClick={del}>Delete my account and data</button></p>
    </div>
  );
}

function useLoad<T>(path: string, key: string) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => {
    const r = await api(path);
    if (r.ok) setData(r.data[key]); else setErr(r.data?.message ?? "Could not load.");
  }, [path, key]);
  useEffect(() => { load(); }, [load]);
  return { data, err, reload: load };
}

function JobLine({ j }: { j: any }) {
  return <li className="card"><h3><Link href={`/jobs/${j.id}`}>{j.title}</Link></h3>
    <div className="meta"><span>{j.employer ?? "Employer not stated"}</span><span>{j.location_text ?? "Location not stated"}</span></div></li>;
}

function Recs() {
  const [path, setPath] = useState<string | null>(null);
  useEffect(() => { api("/api/cv").then((r) => setPath(`/api/recommendations${r.data?.cvs?.[0] ? `?cv_id=${r.data.cvs[0].id}` : ""}`)); }, []);
  const { data, err } = useLoad<any[]>(path ?? "/api/recommendations", "recommendations");
  if (!path) return <p className="hint">Loading…</p>;
  if (err) return <div className="error">{err}</div>;
  if (!data) return <p className="hint">Loading…</p>;
  if (!data.length) return <div className="empty">No recommendations yet. Add skills to your profile or upload a CV.</div>;
  return <ul className="list">{data.map((r) => (
    <li key={r.job.id} className="card"><h3><Link href={`/jobs/${r.job.id}`}>{r.job.title}</Link></h3>
      <div className="meta"><span>{r.job.employer ?? "Employer not stated"}</span><span>Match {r.match_score}/100 ({r.confidence} confidence)</span></div>
      <p className="why">Why: {r.reasons.join("; ")}</p>
      {r.missing_or_unverified?.length > 0 && <p className="hint">Not found in your CV: {r.missing_or_unverified.join(", ")}</p>}
    </li>))}
    <li className="hint">Scores are decision support based on stated requirements, not a prediction of being hired.</li></ul>;
}

function Saved() {
  const { data, err } = useLoad<any[]>("/api/saved", "jobs");
  if (err) return <div className="error">{err}</div>;
  if (!data) return <p className="hint">Loading…</p>;
  return data.length ? <ul className="list">{data.map((j) => <JobLine key={j.id} j={j} />)}</ul> : <div className="empty">No saved jobs yet.</div>;
}

function Apps() {
  const { data, err, reload } = useLoad<any[]>("/api/applications", "applications");
  const [title, setTitle] = useState("");
  async function add(e: React.FormEvent) { e.preventDefault(); const r = await api("/api/applications", "POST", { job_title: title, status: "interested" }); if (r.ok) { setTitle(""); reload(); } }
  async function setStatus(id: number, status: string) { await api(`/api/applications/${id}`, "PATCH", { status }); reload(); }
  async function remove(id: number) { await api(`/api/applications/${id}`, "DELETE"); reload(); }
  if (err) return <div className="error">{err}</div>;
  return <div>
    <form onSubmit={add} className="search"><div className="field"><label htmlFor="at">Track a role (applied elsewhere?)</label>
      <input id="at" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} /></div><button className="btn">Add</button></form>
    <p className="hint">We never submit applications for you. This is your own tracker.</p>
    {!data ? <p className="hint">Loading…</p> : data.length === 0 ? <div className="empty">No applications tracked yet.</div> :
      <ul className="list">{data.map((a) => <li key={a.id} className="card"><h3>{a.job_title}</h3>
        <div className="meta"><span>{a.employer ?? "Employer not stated"}</span></div>
        <div className="chips" style={{ marginTop: 8 }}>
          <select aria-label="Status" value={a.status} onChange={(e) => setStatus(a.id, e.target.value)}>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
          <button className="chip" onClick={() => remove(a.id)}>Remove</button></div></li>)}</ul>}
  </div>;
}

function Alerts() {
  const { data, err, reload } = useLoad<any[]>("/api/alerts", "alerts");
  const [msg, setMsg] = useState<string | null>(null);
  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget);
    const kw = String(f.get("kw") ?? "").split(",").map((s) => s.trim()).filter(Boolean);
    const r = await api("/api/alerts", "POST", { name: f.get("name"), filters: { keywords: kw, province: f.get("province") || undefined }, frequency: f.get("freq"), channel: "in_app" });
    setMsg(r.ok ? "Alert created." : r.data?.message ?? "Could not create alert."); if (r.ok) { reload(); (e.target as HTMLFormElement).reset(); }
  }
  async function remove(id: number) { await api(`/api/alerts/${id}`, "DELETE"); reload(); }
  if (err) return <div className="error">{err}</div>;
  return <div>
    <form onSubmit={add} className="search">
      <div className="field"><label htmlFor="an">Name</label><input id="an" name="name" maxLength={80} /></div>
      <div className="field"><label htmlFor="ak">Keywords (comma separated)</label><input id="ak" name="kw" required /></div>
      <div className="field"><label htmlFor="ap">Province (optional)</label><input id="ap" name="province" /></div>
      <div className="field"><label htmlFor="af">How often</label><select id="af" name="freq" defaultValue="daily"><option>instant</option><option>daily</option><option>weekly</option></select></div>
      <button className="btn">Create alert</button></form>
    {msg && <p className="hint" role="status">{msg}</p>}
    <p className="hint">Alerts appear in your account. Email delivery is not switched on yet.</p>
    {data && data.length > 0 && <ul className="list">{data.map((a) => <li key={a.id} className="card"><h3>{a.name}</h3>
      <div className="meta"><span>{a.frequency}</span><span>{(a.filters.keywords ?? []).join(", ")}</span></div>
      <button className="chip" onClick={() => remove(a.id)}>Delete</button></li>)}</ul>}
  </div>;
}

function Cvs() {
  const { data, err, reload } = useLoad<any[]>("/api/cv", "cvs");
  const [msg, setMsg] = useState<string | null>(null);
  async function up(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return;
    const r = await uploadCv(f); setMsg(r.ok ? "CV added." : r.data?.message ?? "Upload failed."); if (r.ok) reload(); e.target.value = "";
  }
  async function remove(id: number) { await api(`/api/cv/${id}`, "DELETE"); reload(); }
  if (err) return <div className="error">{err}</div>;
  return <div>
    <div className="field"><label htmlFor="cvf">Upload a CV (PDF, DOCX or TXT)</label><input id="cvf" type="file" accept=".pdf,.docx,.txt" onChange={up} /></div>
    <p className="hint">We keep only the extracted text (not the original file), delete it automatically after 30 days, and you can delete it any time. AI features are not switched on yet.</p>
    {msg && <p className="hint" role="status">{msg}</p>}
    {data && data.length > 0 && <ul className="list">{data.map((c) => <li key={c.id} className="card"><h3>{c.label ?? `CV ${c.id}`}</h3>
      <div className="meta"><span>Expires {new Date(c.expires_at).toLocaleDateString("en-ZA")}</span></div>
      <button className="chip" onClick={() => remove(c.id)}>Delete</button></li>)}</ul>}
  </div>;
}

function Profile() {
  const [skills, setSkills] = useState(""); const [modes, setModes] = useState<string[]>([]); const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { api("/api/profile").then((r) => { if (r.ok) { setSkills((r.data.profile.skills ?? []).join(", ")); setModes(r.data.profile.work_modes ?? []); } }); }, []);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    const r = await api("/api/profile", "PUT", { skills: skills.split(",").map((s) => s.trim()).filter(Boolean), work_modes: modes });
    setMsg(r.ok ? "Saved." : r.data?.message ?? "Could not save.");
  }
  const toggle = (m: string) => setModes((x) => x.includes(m) ? x.filter((y) => y !== m) : [...x, m]);
  return <form onSubmit={save} className="search">
    <div className="field"><label htmlFor="sk">Skills (comma separated)</label><input id="sk" value={skills} onChange={(e) => setSkills(e.target.value)} /></div>
    <fieldset><legend className="hint">Work modes you prefer</legend>
      {["remote", "hybrid", "on_site"].map((m) => <label key={m} style={{ marginRight: 14 }}><input type="checkbox" checked={modes.includes(m)} onChange={() => toggle(m)} /> {m.replace("_", "-")}</label>)}</fieldset>
    <p className="hint">We do not ask for or use gender, race, age or other protected characteristics.</p>
    <button className="btn">Save profile</button>{msg && <span className="hint" role="status"> {msg}</span>}</form>;
}
