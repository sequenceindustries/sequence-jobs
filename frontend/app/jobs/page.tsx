import type { Metadata } from "next";
import { JobCard } from "@/components/JobCard";
import { NaturalSearchForm, SearchForm } from "@/components/SearchForm";
import { naturalSearch, searchJobs, type SearchResponse } from "@/lib/api";

export const dynamic = "force-dynamic";

type SP = Promise<Record<string, string | string[] | undefined>>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";

export async function generateMetadata({ searchParams }: { searchParams: SP }): Promise<Metadata> {
  const sp = await searchParams;
  const filtered = Object.keys(sp).length > 0;
  return {
    title: "Jobs in South Africa",
    description: "Browse current South African vacancies with links to the original application.",
    alternates: { canonical: "/jobs" },
    robots: filtered ? { index: false, follow: true } : undefined, // never index arbitrary filter combinations
  };
}

export default async function Jobs({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const nl = one(sp.nl).trim();
  const qs = new URLSearchParams();
  for (const k of ["q", "province", "work_mode", "page"]) if (one(sp[k])) qs.set(k, one(sp[k]));

  let data: SearchResponse | null = null;
  let failed = false;
  let aiNote: string | null = null;
  let interpreted: Record<string, unknown> | null = null;

  if (nl) {
    const r = await naturalSearch(nl);
    if (r.ok) { data = r.data; interpreted = r.data.interpreted_filters; }
    else aiNote = r.aiUnavailable
      ? "AI search is unavailable right now. Please use the keyword search above – it works without AI."
      : "We couldn't run that search. Please try again.";
  } else {
    const r = await searchJobs(qs);
    if (r.ok) data = r.data; else failed = true;
  }

  return (
    <>
      <section className="hero" style={{ paddingBottom: 12 }}>
        <h1 style={{ fontSize: "1.6rem" }}>Jobs</h1>
        <SearchForm q={one(sp.q)} province={one(sp.province)} workMode={one(sp.work_mode)} />
        <NaturalSearchForm nl={nl} />
      </section>
      <section className="section" aria-live="polite">
        {aiNote && <div className="error" role="status">{aiNote}</div>}
        {failed && <div className="error" role="alert">Jobs are temporarily unavailable. Please try again shortly.</div>}
        {interpreted && <p className="hint">Interpreted as filters: {JSON.stringify(interpreted)}</p>}
        {data && (
          <>
            <p className="hint">{data.total} job{data.total === 1 ? "" : "s"} found</p>
            {data.unapplied_filters.length > 0 && <p className="hint">Not applied yet (no reliable data): {data.unapplied_filters.join(", ")}.</p>}
            {data.results.length === 0
              ? <div className="empty">No jobs match. Try fewer filters or different keywords.</div>
              : <ul className="list">{data.results.map((j) => <JobCard key={j.id} job={j} />)}</ul>}
          </>
        )}
      </section>
    </>
  );
}
