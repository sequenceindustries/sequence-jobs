# Job source research (as of 14 Oct 2026)

Status key: **usable** = terms verified permit our use · **candidate** = official and promising, terms still to verify · **blocked** = cannot be used as-is.
Nothing below is a legal opinion; confirm terms with counsel before launch.

| Source | Access method | Status | Findings |
|---|---|---|---|
| Public Service Vacancy Circular (DPSA, published on gov.za) | Weekly PDF, one file per circular | **restricted** | Verified in a browser on 14 Oct 2026. `robots.txt` does not disallow `/sites/default/files/` (only admin, search, user and core paths). **But** the gov.za terms of use allow copying/distribution only for non-commercial informational purposes; commercial use needs prior written permission from GCIS (electronic@gcis.gov.za) and must carry the notice "© GCIS2018: ALL RIGHTS RESERVED". Framing gov.za pages is prohibited; linking is welcomed. An advertising-funded aggregator is commercial, so we must not copy circular content until permission is on file. Official, weekly, structured, so it is still the best first source once permitted. No per-post application URL exists. Connector built; source is `terms_status = restricted`, `enabled = false`, and the ingestion service refuses to run restricted sources even with `--force`. |
| Adzuna API (`api.adzuna.com`) | Official REST API, needs app_id/app_key | **blocked (for now)** | Terms allow a 14-day trial for commercial users; ongoing commercial use needs a licence or written consent. Default limits 25/min, 250/day, 1,000/week, 2,500/month. Requires an "Adzuna" attribution label on every listing, and data must be removed on termination (no caching allowance stated). Whether South Africa (`za`) is a supported country was not confirmed from the public docs. Revisit if we want to apply for a commercial licence. |
| Remotive API | Public JSON API | **blocked** | Docs forbid submitting Remotive jobs to third-party aggregators/search engines; data is delayed 24 h; max 4 requests/day. Their terms also bar copying/republishing listings and building a database of listings. Not usable for our product. |
| Careers24, PNet, CareerJunction and similar boards | HTML sites | **not used** | No official API or feed was found. Third-party scrapers exist (e.g. on Apify) but scraping is not assumed to be permitted; their terms were not reviewed and we do not scrape. Approach them for partner/XML feeds instead. |
| Employer career pages, universities, municipalities | Varies | **to research** | Best path: ask employers for a vacancy feed, or use ones that publish an official RSS/JSON feed. The generic `json_feed` connector is ready for these once a feed's terms are confirmed. |

## Next verification steps (human or unrestricted network needed)
1. Send the GCIS permission request (draft in `docs/GCIS_PERMISSION_REQUEST.md`) and ask which department owns the circular content; identify the stable listing page that enumerates circulars. A link-only option (title + link to the gov.za PDF, no copied content) may be acceptable without permission; confirm with counsel.
2. Run the DPSA connector against a real circular and compare parsed posts with the PDF by eye (the parser is only tested on a synthetic fixture so far).
3. Request partner feeds from SA job boards and a licence quote from Adzuna.
