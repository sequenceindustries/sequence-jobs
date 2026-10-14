"use client";
import { useState } from "react";
import { api } from "@/lib/client";

export function AuthForm() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true); setMsg(null);
    const r = await api(`/api/auth/${mode}`, "POST", { email: f.get("email"), password: f.get("password") });
    setBusy(false);
    if (r.ok) { window.location.href = "/account"; return; }
    setMsg(r.data?.message ?? "Something went wrong. Please try again.");
  }

  return (
    <form className="search" onSubmit={submit} style={{ maxWidth: 420 }}>
      <h1 style={{ fontSize: "1.4rem", margin: 0 }}>{mode === "login" ? "Log in" : "Create your account"}</h1>
      <div className="field"><label htmlFor="email">Email</label><input id="email" name="email" type="email" required autoComplete="email" /></div>
      <div className="field"><label htmlFor="password">Password {mode === "register" && "(at least 10 characters)"}</label>
        <input id="password" name="password" type="password" required minLength={mode === "register" ? 10 : 1}
               autoComplete={mode === "login" ? "current-password" : "new-password"} /></div>
      {msg && <div className="error" role="alert">{msg}</div>}
      <button className="btn" disabled={busy}>{mode === "login" ? "Log in" : "Register"}</button>
      <button type="button" className="chip" onClick={() => { setMode(mode === "login" ? "register" : "login"); setMsg(null); }}>
        {mode === "login" ? "No account? Register" : "Have an account? Log in"}
      </button>
      <p className="hint">Your account is optional. Searching jobs never requires one.</p>
    </form>
  );
}
