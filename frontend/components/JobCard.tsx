import Link from "next/link";
import { formatDate, formatSalary, type Job } from "@/lib/api";

const MODE: Record<string, string> = { remote: "Remote", hybrid: "Hybrid", on_site: "On-site" };

export function JobCard({ job }: { job: Job }) {
  const salary = formatSalary(job);
  const place = job.location_text ?? job.city ?? job.province;
  return (
    <li className="card">
      <h3><Link href={`/jobs/${job.id}`}>{job.title}</Link></h3>
      <div className="meta">
        <span>{job.employer ?? <span className="unknown">Employer not stated</span>}</span>
        {place && <span>{place}</span>}
        {job.published_at && <span>Posted {formatDate(job.published_at)}</span>}
        {job.closing_at && <span>Closes {formatDate(job.closing_at)}</span>}
      </div>
      <div className="tags">
        {job.is_dev_data && <span className="tag dev">DEV DATA – not a real vacancy</span>}
        {job.work_mode && <span className="tag">{MODE[job.work_mode]}</span>}
        {job.employment_type && <span className="tag">{job.employment_type}</span>}
        {salary ? <span className="tag">{salary}</span> : <span className="tag" style={{ opacity: 0.7 }}>Salary not stated</span>}
      </div>
      {job.match_reasons.length > 0 && <p className="why">Why it matched: {job.match_reasons.join("; ")}.</p>}
      <p className="why">Source: {job.source_name}</p>
    </li>
  );
}
