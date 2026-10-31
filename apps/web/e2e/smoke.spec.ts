import { expect, test } from "@playwright/test";

// End-to-end smoke tests against a RUNNING full stack (api + web). These exercise
// the real server-rendered dashboard, so they tolerate an empty/partial dataset:
// assertions that require rows are skipped when the board has no data yet (the
// startup warm-up pass may still be in flight on a fresh compose up).

test.describe("dashboard smoke", () => {
  test("renders the overview board", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Overview" }),
    ).toBeVisible({ timeout: 30_000 });
  });

  test("links out to the OpenAPI docs", async ({ page }) => {
    await page.goto("/");
    // The header "API" link points at `${NEXT_PUBLIC_API_URL}/docs`. We assert the
    // href is well-formed (ends in /docs) rather than pinning an exact host, so
    // the check holds whether run against compose (:3646) or a local dev server.
    const apiLink = page.getByRole("link", { name: "API", exact: true });
    await expect(apiLink).toHaveAttribute("href", /\/docs$/);
  });

  test("opens a protocol detail page", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible({
      timeout: 30_000,
    });
    const protocolLinks = page.locator('main a[href^="/protocols/"]');
    test.skip(
      (await protocolLinks.count()) === 0,
      "no protocols rendered yet (empty dataset)",
    );
    await protocolLinks.first().click();
    await expect(page).toHaveURL(/\/protocols\/[^/]+$/);
    // Generous timeout: a cold `next dev` compiles /protocols/[slug] on the
    // first navigation, which can outlast the 5s default.
    await expect(page.getByRole("heading").first()).toBeVisible({
      timeout: 15_000,
    });
  });
});
