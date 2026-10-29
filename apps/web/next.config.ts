import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Minimal self-contained server output for the multi-stage Docker runtime
  // image (copies .next/standalone + static + public, runs `node server.js`).
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
