import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end smoke + interaction tests for the DeFiScope web app.
 *
 * These run against an ALREADY-RUNNING full stack (api + web), not a mocked one:
 *   docker compose up --build   # web published on http://localhost:4000
 *   npm run test:e2e
 *
 * Override the target with E2E_BASE_URL (e.g. http://localhost:3000 when running
 * `next dev` locally with the API up on :8000).
 */
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:4000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
