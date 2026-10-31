import fs from "node:fs";
import path from "node:path";

import { expect, test as setup } from "@playwright/test";

/**
 * Playwright setup project: sign in once and persist the cookie jar.
 *
 * The existing `smoke.spec.ts` and `protocol-table.spec.ts` are deliberately
 * unchanged. They now run in a context that already holds a session, so the
 * assertion they make — "the board renders" — keeps meaning the same thing
 * even though the board is now an authorized view.
 *
 * Admin is the right identity for those: it bypasses every ABAC gate, so the
 * only thing that can make them fail is the app actually breaking. Scoping is
 * asserted separately, in `roles.spec.ts`, where it is the subject.
 */
export const ADMIN_STATE = path.resolve(__dirname, ".auth/admin.json");

const EMAIL = process.env.E2E_EMAIL ?? "admin@demo";
const PASSWORD = process.env.E2E_PASSWORD ?? "defiscope-demo";

setup("authenticate as the demo admin", async ({ page }) => {
  fs.mkdirSync(path.dirname(ADMIN_STATE), { recursive: true });

  await page.goto("/login");

  // With `DEFISCOPE_AUTH_MODE=off` the login page bounces straight to the board
  // and there is no session to store. Persist the (empty) jar and move on so
  // the dependent projects stay runnable in that mode.
  if (!new URL(page.url()).pathname.startsWith("/login")) {
    await page.context().storageState({ path: ADMIN_STATE });
    return;
  }

  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();

  // A failed sign-in leaves us on /login with an inline error; assert we left.
  await expect(page).not.toHaveURL(/\/login/, { timeout: 30_000 });
  await page.context().storageState({ path: ADMIN_STATE });
});
