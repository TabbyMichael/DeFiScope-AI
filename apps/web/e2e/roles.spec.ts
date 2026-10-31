import { expect, test } from "@playwright/test";

/**
 * The authorization tour, asserted end to end.
 *
 * These deliberately start from an EMPTY cookie jar: `smoke.spec.ts` and
 * `protocol-table.spec.ts` reuse an admin session, which is exactly the
 * identity that would hide every gate from them.
 *
 * Each case asserts a denial or a narrowing — never just "it didn't crash" —
 * so a regression that quietly removes a gate turns one of these red.
 */
test.use({ storageState: { cookies: [], origins: [] } });

const PASSWORD = process.env.E2E_PASSWORD ?? "defiscope-demo";

async function signIn(page: import("@playwright/test").Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/, { timeout: 30_000 });
}

/** Open the header user menu (the only control labelled with the subject). */
async function openUserMenu(page: import("@playwright/test").Page, email: string) {
  await page.getByRole("button", { name: `Signed in as ${email}` }).click();
}

function authDisabled(page: import("@playwright/test").Page): boolean {
  return !new URL(page.url()).pathname.startsWith("/login");
}

test.describe("authorization", () => {
  test("an anonymous visitor is sent to /login and asked to come back", async ({
    page,
  }) => {
    await page.goto("/alerts");
    if (authDisabled(page)) test.skip(true, "DEFISCOPE_AUTH_MODE=off");
    const url = new URL(page.url());
    expect(url.pathname).toBe("/login");
    expect(url.searchParams.get("next")).toBe("/alerts");
  });

  test("the scoped analyst sees Lending + Dexes, not the whole board", async ({
    page,
  }) => {
    await page.goto("/login");
    if (authDisabled(page)) test.skip(true, "DEFISCOPE_AUTH_MODE=off");

    await signIn(page, "analyst@demo");

    // The header states the ABAC attributes the API will enforce. This is the
    // observable difference between analyst and every other demo account.
    // Category order is presentation detail (the API returns a set), so assert
    // membership rather than a specific ordering.
    const trigger = page.getByRole("button", { name: "Signed in as analyst@demo" });
    await expect(trigger).toBeVisible({ timeout: 30_000 });
    await expect(trigger).toContainText(/Lending/);
    await expect(trigger).toContainText(/Dexes/);
    await expect(trigger).not.toContainText(/all categories/);
    await expect(trigger).toContainText(/clearance 1/);
  });

  test("switching to risk officer widens clearance and sign-out ends the session", async ({
    page,
  }) => {
    await page.goto("/login");
    if (authDisabled(page)) test.skip(true, "DEFISCOPE_AUTH_MODE=off");

    await signIn(page, "viewer@demo");
    await expect(
      page.getByRole("button", { name: "Signed in as viewer@demo" }),
    ).toBeVisible({ timeout: 30_000 });

    await openUserMenu(page, "viewer@demo");
    await page.getByText("Switch role: demo").waitFor();
    await page.getByRole("menuitem", { name: /Risk officer/ }).click();

    // A different principal: the new session re-renders as clearance 2.
    const officer = page.getByRole("button", { name: "Signed in as officer@demo" });
    await expect(officer).toBeVisible({ timeout: 30_000 });
    await expect(officer).toContainText(/clearance 2/);

    await openUserMenu(page, "officer@demo");
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    // Sign-out ends at the public landing page, not at /login: the visitor has
    // not asked to sign in again, they asked to leave.
    await expect(page).toHaveURL(/\/welcome/, { timeout: 30_000 });
    await expect(
      page.getByRole("heading", { level: 1, name: /Protocol risk/ }),
    ).toBeVisible({ timeout: 30_000 });

    // The session really is gone, not just visually hidden: a deep link is
    // intercepted and survives as ?next=.
    await page.goto("/alerts");
    await expect(page).toHaveURL(/\/login\?next=%2Falerts/, { timeout: 30_000 });
  });

  test("a viewer sees the withheld count rather than an empty alert feed", async ({
    page,
  }) => {
    await page.goto("/login");
    if (authDisabled(page)) test.skip(true, "DEFISCOPE_AUTH_MODE=off");

    await signIn(page, "viewer@demo");
    await page.goto("/alerts");
    await expect(page.getByRole("heading", { name: /Monitoring/ })).toBeVisible({
      timeout: 30_000,
    });

    // Only meaningful when a critical alert exists in this data window. When it
    // does, the banner must name the count and the clearance it would need —
    // the whole point is that silence is never shown in place of a denial.
    // Match the container (role=status), not the inner count span: the sentence
    // naming the required clearance lives in the parent paragraph.
    const banner = page
      .getByRole("status")
      .filter({ hasText: /alerts? withheld/ });
    if ((await banner.count()) === 0) {
      test.skip(true, "no critical alerts in the current window");
    }
    await expect(banner.first()).toContainText(/clearance 2 required/);
  });
});
