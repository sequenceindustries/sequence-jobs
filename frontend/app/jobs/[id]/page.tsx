import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { formatDate, formatSalary, getJob, type JobDetail } from "@/lib/api";

export const dynamic = "force-dynamic";
type P = Promise<{ id: string }>;

export async function generateMetadata({ params }: { params: P }): Promise<Metadata> {
  const { id } = await params;
  const r = await getJob(id);
  if (!r.ok) return { title: "Job not found", robots: { index: false } };
  const j = r.data;
  return {
    title: `${j.title}${j.employer ? ` at ${j.employer}` : ""}`,
    description: `${j.title}${j.location_text ? ` in ${j.location_text}` : ""}. View details and apply via the original source.`,
    alternates: { canonical: `/jobs/${j.id}` },
    robots: j.is_dev_data || j.status !== "active" ? { index: false, follow: true } : undefined,
  };
}

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

/** JobPosting structured data only from facts we actually hold. Omitted entirely if required fields are missing. */
function jobPostingLd(j: JobDetail) {
  if (j.is_dev_data || j.status !== "active") return null;
  if (j.closing_at && new Date(j.closing_at) < new Date()) return null;
  if (!j.employer || !j.description || !j.published_at || !(j.city || j.location_text)) return null;
  const ld: Record<string, unknown> = {
    "@context": "https://schema.org", "@type": "JobPosting", title: j.title, description: j.description,
    datePosted: j.published_at, hiringOrganization: { "@type": "Organization", name: j.employer },
    jobLocation: { "@type": "Place", address: { "@type": "PostalAddress", addressLocality: j.city ?? j.location_text,
      ...(j.province ? { addressRegion: j.province } : {}), addressCountry: "ZA" } },
    url: `${SITE}/jobs/${j.id}`,
  };
  if (j.closing_at) ld.validThrough = j.closing_at;
  if (j.work_mode === "remote") ld.jobLocationType = "TELECOMMUTE";
  if (j.salary_min && j.salary_currency && j.salary_period) {
    ld.baseSalary = { "@type": "MonetaryAmount", currency: j.salary_currency, value: {
      "@type": "QuantitativeValue", minValue: Number(j.salary_min), ...(j.salary_max ? { maxValue: Number(j.salary_max) } : {}),
      unitText: j.salary_period.toUpperCase() } };
  }
  return ld;
}

const Unknown = () => <span className="unknown">Not stated</span>;

export default async function JobPage({ params }: { params: P }) {
  const { id } = await params;
  const r = await getJob(id);
  if (!r.ok) {
    if (r.status === 404 || r.status === 301) notFound();
    return <div className="error" role="alert" style={{ marginTop: 24 }}>This job is temporarily unavailable.</div>;
  }
  const j = r.data;
  const salary = formatSalary(j);
  const ld = jobPostingLd(j);
  const breadcrumb = { "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement: [
    { "@type": "ListItem", position: 1, name: "Home", item: SITE }, { "@type": "ListItem", position: 2, name: "Jobs", item: `${SITE}/jobs` },
    { "@type": "ListItem", position: 3, name: j.title } ] };
  const applyHref = j.application_url ?? j.source_url;

  return (
    <article className="detail" style={{ paddingTop: 20 }}>
      {ld && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(ld).replace(/</g, "\\u003c") }} />}
      {!j.is_dev_data && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumb).replace(/</g, "\\u003c") }} />}
      {j.status !== "active" && <div className="notice" style={{ borderRadius: 8 }}>This vacancy is no longer listed as open. Check the original source before applying.</div>}
      <nav aria-label="Breadcrumb" className="hint"><Link href="/">Home</Link> › <Link href="/jobs">Jobs</Link></nav>
      {j.is_dev_data && <div className="notice" style={{ borderRadius: 8 }}>DEV DATA – synthetic, not a real vacancy.</div>}
      <h1>{j.title}</h1>
      <p className="meta">{j.employer ?? "Employer not stated"} · {j.location_text ?? "Location not stated"}</p>
      <a className="btn apply" href={applyHref} target="_blank" rel="noopener noreferrer nofollow">
        {j.application_url ? "Apply at the original source" : "View the original listing"}
      </a>
      <dl className="facts">
        <div><dt>Salary</dt><dd>{salary ?? <Unknown />}</dd></div>
        <div><dt>Employment type</dt><dd>{j.employment_type ?? <Unknown />}</dd></div>
        <div><dt>Work mode</dt><dd>{j.work_mode?.replace("_", "-") ?? <Unknown />}</dd></div>
        <div><dt>Posted</dt><dd>{formatDate(j.published_at) ?? <Unknown />}</dd></div>
        <div><dt>Closing date</dt><dd>{formatDate(j.closing_at) ?? <Unknown />}</dd></div>
        <div><dt>Reference</dt><dd>{j.reference_no ?? <Unknown />}</dd></div>
        <div><dt>Source</dt><dd><a href={j.source_url} rel="noopener noreferrer nofollow">{j.source_name}</a></dd></div>
        <div><dt>Last verified</dt><dd>{formatDate(j.last_verified_at)}</dd></div>
      </dl>
      {j.description && <><h2>Description</h2><p className="body">{j.description}</p></>}
      {j.requirements_text && <><h2>Requirements</h2><p className="body">{j.requirements_text}</p></>}
      {j.application_instructions && <><h2>How to apply</h2><p className="body">{j.application_instructions}</p></>}
      <p className="hint">{j.disclaimer}</p>
    </article>
  );
}
