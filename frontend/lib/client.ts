"use client";
// Browser-side API helper: same-origin, cookie session, CSRF token header on unsafe methods.
let token: string | null = null;

async function csrf(): Promise<string> {
  if (!token) token = (await (await fetch("/api/auth/csrf", { credentials: "same-origin" })).json()).csrf_token;
  return token!;
}

export type ApiResult<T = any> = { ok: boolean; status: number; data: T };

export async function api<T = any>(path: string, method = "GET", body?: unknown): Promise<ApiResult<T>> {
  const headers: Record<string, string> = {};
  if (method !== "GET") { headers["X-CSRF-Token"] = await csrf(); headers["Content-Type"] = "application/json"; }
  try {
    const res = await fetch(path, { method, headers, credentials: "same-origin", body: body === undefined ? undefined : JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (data?.csrf_token) token = data.csrf_token;
    return { ok: res.ok, status: res.status, data };
  } catch {
    return { ok: false, status: 0, data: { error: "network", message: "Cannot reach the server." } as T };
  }
}

export async function uploadCv(file: File): Promise<ApiResult> {
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/cv", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": await csrf() }, body: fd });
    return { ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) };
  } catch {
    return { ok: false, status: 0, data: { message: "Cannot reach the server." } };
  }
}
