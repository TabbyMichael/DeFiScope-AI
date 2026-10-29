import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Ignore Next's build output, installed deps, and the Playwright e2e suite
    // (those run via `npm run test:e2e`, not vitest).
    exclude: ["**/node_modules/**", ".next/**", "e2e/**"],
  },
  resolve: {
    alias: {
      // Mirror tsconfig paths: "@/*" -> repo-relative from apps/web.
      "@": path.resolve(__dirname, "."),
    },
  },
});
