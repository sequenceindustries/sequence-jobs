// Server-side API client. Real job data only: if the API is down we say so, we never fabricate listings.

export type Job = {
  id: number;
  title: string;
  employer: string | null;
  location_text: string | null;
  city: string | null;
  province: string | null;
  work_mode: "on_site" | "hybrid" | "remote" | null;
  employment_type: string | null;
  salary_min: string | null;
  salary_max: string | null;
  salary_currency: string | null;
  salary_period: "hour" | "month" | "year" | null;
  salary_raw: string | null;
  published_at: string | null;
  closing_at: string | null;
  source_url: string;
  application_url: string | null;
  last_verified_at: string;
  is_dev_data: boolean;
  status: "active" | "expired" | "closed" | "removed";
  source_name: string;
  match_reasons: string[];
  unavailable_fields: string[];
};

export type JobDetail = Job & {
  description: string | null;
  requirements_text: string | null;
  application_instructions: string | null;
  reference_no: string | null;
  disclaimer: string;
};

export type SearchResponse = {
  total: number;
  page: number;
  per_page: number;
  results: Job[];
  data_notice: string | null;
  unapplied_filters: string[];
};

const API_URL = process.env.API_URL ?? "http://127.0.0.1:5000";

async function get<T>(path: string): Promise<{ ok: true; data: T } | { ok: false; status: number }> {
  try {
    const res = await fetch(`${API_URL}${path}`, { cache: "no-store", signal: AbortSignal.timeout(8000) });
    if (!res.ok) return { ok: false, status: res.status };
    return { ok: true, data: (await res.json()) as T };
  } catch {
    return { ok: false, status: 0 };
  }
}

export const searchJobs = (qs: URLSearchParams) => get<SearchResponse>(`/api/jobs?${qs.toString()}`);
export const getJob = (id: string) => get<JobDetail>(`/api/jobs/${encodeURIComponent(id)}`);

export function formatSalary(j: Pick<Job, "salary_min" | "salary_max" | "salary_period" | "salary_raw">): string | null {
  if (j.salary_min == null) return null; // unknown stays unknown
  const n = (v: string) => `R${Number(v).toLocaleString("en-ZA", { maximumFractionDigits: 0 })}`;
  const range = j.salary_max && j.salary_max !== j.salary_min ? `${n(j.salary_min)} – ${n(j.salary_max)}` : n(j.salary_min);
  const per = j.salary_period === "month" ? " per month" : j.salary_period === "year" ? " per year" : j.salary_period === "hour" ? " per hour" : "";
  return range + per;
}

export function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric", timeZone: "Africa/Johannesburg" });
}

export const PROVINCES = [
  "Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
  "Mpumalanga", "Northern Cape", "North West", "Western Cape",
];

export type NaturalResult =
  | { ok: true; data: SearchResponse & { interpreted_filters: Record<string, unknown> } }
  | { ok: false; aiUnavailable: boolean };

export async function naturalSearch(query: string): Promise<NaturalResult> {
  try {
    const res = await fetch(`${API_URL}/api/search/natural`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query }),
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    if (res.ok) return { ok: true, data: await res.json() };
    return { ok: false, aiUnavailable: res.status === 503 };
  } catch {
    return { ok: false, aiUnavailable: false };
  }
}
