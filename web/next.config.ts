import type { NextConfig } from "next";

// Static export: FastAPI serves web/out from the same origin as the API.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  // In `next dev`, send /api to the local FastAPI server.
  ...(process.env.NODE_ENV === "development" && {
    async rewrites() {
      return [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }];
    },
  }),
};

export default nextConfig;
