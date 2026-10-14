import { PROVINCES } from "@/lib/api";

export function SearchForm({ q = "", province = "", workMode = "" }: { q?: string; province?: string; workMode?: string }) {
  return (
    <form className="search" action="/jobs" method="get" role="search">
      <div className="row">
        <div className="field">
          <label htmlFor="q">Job title, skill or employer</label>
          <input id="q" name="q" defaultValue={q} placeholder="e.g. graphic designer" autoComplete="off" />
        </div>
        <div className="field">
          <label htmlFor="province">Province</label>
          <select id="province" name="province" defaultValue={province}>
            <option value="">All provinces</option>
            {PROVINCES.map((p) => <option key={p}>{p}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="work_mode">Work mode</label>
          <select id="work_mode" name="work_mode" defaultValue={workMode}>
            <option value="">Any</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="on_site">On-site</option>
          </select>
        </div>
        <button className="btn" type="submit">Search jobs</button>
      </div>
    </form>
  );
}

export function NaturalSearchForm({ nl = "" }: { nl?: string }) {
  return (
    <form className="search" action="/jobs" method="get" style={{ marginTop: 12 }}>
      <div className="field">
        <label htmlFor="nl">Or describe the job you want (AI search)</label>
        <input id="nl" name="nl" defaultValue={nl} maxLength={300}
          placeholder="e.g. junior graphic design jobs in Johannesburg that don't need 5 years' experience" />
        <p className="hint">AI only turns your words into filters. Results always come from real listings.</p>
      </div>
      <button className="btn" type="submit">Search with AI</button>
    </form>
  );
}
