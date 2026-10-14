"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";

// Read-mostly admin view. All data comes from /api/admin/*, which enforces the admin role server-side.
export function AdminDash() {
  const [d, setD] = useState<any>(null);
  const [state, setState] = useState<"loading" | "denied" | "ok">("loading");
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    const keys = ["stats", "sources", "runs", "ai-usage", "data-quality", "audit"];
    const rs = await Promise.all(keys.map((k) => api(`/api/admin/${k}`)));
    if (rs.some((r) => r.status === 401 || r.status === 403)) { setState("denied"); return; }
    setD(Object.fromEntries(keys.map((k, i) => [k, rs[i].data]))); setState("ok");
  }
  useEffect(() => { load(); }, []);

  async function toggle(slug: string, enabled: boolean) {
    const r = await api(`/api/admin/sources/${slug}`, "PATCH", { enabled });
    setMsg(r.ok ? `${slug} ${enabled ? "enabled" : "disabled"}.` : r.data?.message ?? "Refused."); load();
  }
  async function run(slug: string) { const r = await api(`/api/admin/sources/${slug}/run`, "POST"); setMsg(`${slug}: ${r.data?.status}${r.data?.reason ? " – " + r.data.reason : ""}`); load(); }

  if (state === "loading") return <p className="hint">Loading…</p>;
  if (state === "denied") return <div className="error" role="alert">Admin access required. <a href="/login">Log in</a> with an admin account.</div>;
  const s = d.stats;
  return <div className="section">
    <h1 style={{ fontSize: "1.5rem" }}>Admin</h1>
    {msg && <p className="hint" role="status">{msg}</p>}
    <h2>Overview</h2>
    <p>{s.jobs_by_status.map((r: any) => `${r.status}: ${r.n}`).join(" · ") || "No jobs"} · new (24h): {s.new_last_24h} · duplicates: {s.duplicates} · needs review: {s.needs_review} · users: {s.users}</p>
    <h2>Sources</h2>
    <ul className="list">{d.sources.sources.map((x: any) => <li key={x.slug} className="card"><h3>{x.slug} {x.is_dev_data && <span className="tag dev">DEV</span>}</h3>
      <div className="meta"><span>terms: {x.terms_status}</span><span>health: {x.health}</span><span>enabled: {String(x.enabled)}</span><span>last success: {x.last_success_at ?? "never"}</span></div>
      <div className="chips" style={{ marginTop: 8 }}>
        <button className="chip" onClick={() => toggle(x.slug, !x.enabled)}>{x.enabled ? "Disable" : "Enable"}</button>
        <button className="chip" onClick={() => run(x.slug)}>Run now</button></div>
      {x.terms_status !== "verified_permitted" && <p className="hint">Cannot be enabled until terms are verified as permitted.</p>}</li>)}</ul>
    <h2>Data quality (active jobs)</h2>
    <ul>{Object.entries(d["data-quality"].checks).map(([k, v]: any) => <li key={k}>{k.replaceAll("_", " ")}: {v.count}</li>)}</ul>
    <h2>AI usage (30 days)</h2>
    {d["ai-usage"].last_30_days.length === 0 ? <p className="hint">No AI calls recorded.</p> :
      <ul>{d["ai-usage"].last_30_days.map((r: any, i: number) => <li key={i}>{r.task} / {r.status}: {r.calls} calls, est. cost {r.est_cost_usd ?? "unknown"}</li>)}</ul>}
    <h2>Recent ingestion runs</h2>
    <ul>{d.runs.runs.slice(0, 10).map((r: any) => <li key={r.id}>{r.slug}: {r.status}, fetched {r.fetched}, errors {r.errors}</li>)}</ul>
    <h2>Audit log</h2>
    <ul>{d.audit.entries.slice(0, 20).map((e: any) => <li key={e.id}>{e.at} – {e.action} {e.target ?? ""}</li>)}</ul>
  </div>;
}
