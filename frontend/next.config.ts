import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://127.0.0.1:5000";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  // Same-origin proxy so the session cookie and CSRF header work without CORS.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
