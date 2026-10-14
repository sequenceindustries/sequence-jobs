import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";

const site = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(site),
  title: { default: "Sequence Jobs – AI-powered job search for South Africa", template: "%s | Sequence Jobs" },
  description: "Find South African jobs from verified sources, with AI help to match, understand and apply.",
  alternates: { canonical: "/" },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const nonProd = process.env.NODE_ENV !== "production";
  return (
    <html lang="en-ZA">
      <body>
        <a className="skip" href="#main">Skip to content</a>
        {nonProd && <div className="notice" role="status">Development environment – any listings shown are synthetic test data.</div>}
        <header className="site-header">
          <div className="container">
            <Link className="logo" href="/">Sequence<span>Jobs</span></Link>
            <nav className="nav" aria-label="Main"><Link href="/jobs">All jobs</Link><Link href="/jobs?work_mode=remote">Remote</Link></nav>
          </div>
        </header>
        <main id="main" className="container">{children}</main>
        <footer className="footer">
          <div className="container">
            <p>Sequence Jobs lists vacancies advertised by third parties and links to the original source. Sequence Industries (Pty) Ltd is not the employer. AI results are decision support, not a hiring prediction.</p>
          </div>
        </footer>
      </body>
    </html>
  );
}
