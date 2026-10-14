import Link from "next/link";
import { JobCard } from "@/components/JobCard";
import { NaturalSearchForm, SearchForm } from "@/components/SearchForm";
import { PROVINCES, searchJobs } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const latest = await searchJobs(new URLSearchParams({ per_page: "6" }));
  const remote = await searchJobs(new URLSearchParams({ per_page: "1", work_mode: "remote" }));

  return (
    <>
      <section className="hero">
        <h1>Find South African jobs that actually fit you.</h1>
        <p>We collect vacancies from legitimate sources and link you to the original application. AI helps you search in plain English, check your CV against a role and prepare to apply.</p>
        <SearchForm />
        <NaturalSearchForm />
      </section>

      <section className="section" aria-labelledby="latest">
        <h2 id="latest">Recently listed</h2>
        {!latest.ok ? (
          <div className="error" role="alert">Jobs are temporarily unavailable. Please try again shortly.</div>
        ) : latest.data.results.length === 0 ? (
          <div className="empty">No active listings yet. Sources are being connected and verified.</div>
        ) : (
          <ul className="list">{latest.data.results.map((j) => <JobCard key={j.id} job={j} />)}</ul>
        )}
        {latest.ok && latest.data.total > 6 && <p><Link href="/jobs">See all {latest.data.total} jobs →</Link></p>}
      </section>

      <section className="section" aria-labelledby="browse">
        <h2 id="browse">Browse by province</h2>
        <div className="chips">
          {PROVINCES.map((p) => <Link key={p} className="chip" href={`/jobs?province=${encodeURIComponent(p)}`}>{p}</Link>)}
          <Link className="chip" href="/jobs?work_mode=remote">
            Remote{remote.ok ? ` (${remote.data.total})` : ""}
          </Link>
        </div>
      </section>
    </>
  );
}
