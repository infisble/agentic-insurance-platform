import type { NextConfig } from "next";

const CORE_API_URL = process.env.CORE_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Claim documents are uploaded through Server Actions; the core API accepts up to 20 MB.
  experimental: { serverActions: { bodySizeLimit: "21mb" } },
  // Serve claim documents same-origin so they can be embedded in the case view.
  async rewrites() {
    return [{ source: "/files/:id", destination: `${CORE_API_URL}/documents/:id/file` }];
  },
};

export default nextConfig;
