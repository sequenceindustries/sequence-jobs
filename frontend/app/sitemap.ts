import type { MetadataRoute } from "next";
import { searchJobs } from "@/lib/api";

export const dynamic = "force-dynamic";
const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

// Active, non-dev, non-duplicate listings only (the API already hides merged duplicates).
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const urls: MetadataRoute.Sitemap = [{ url: SITE }, { url: `${SITE}/jobs` }];
  for (let page = 1; page <= 20; page++) {
    const r = await searchJobs(new URLSearchParams({ page: String(page), per_page: "50" }));
    if (!r.ok) break;
    for (const j of r.data.results) {
      if (!j.is_dev_data) urls.push({ url: `${SITE}/jobs/${j.id}`, lastModified: j.last_verified_at });
    }
    if (page * 50 >= r.data.total) break;
  }
  return urls;
}
