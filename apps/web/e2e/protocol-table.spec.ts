import { expect, test } from "@playwright/test";

// The Dashboard's "Protocols" section is now a fully server-paginated view over
// the discovery catalog (the embedded Protocol Explorer). Every control writes
// the current view back to the URL (via the history API), so the assertions here
// verify the client contract - that interactions become server queries - rather
// than coupling to a specific provider dataset that may be empty in a given run.
//
// The Explorer always renders its controls, so the URL-driving tests are robust
// even before any rows load; row/pagination tests skip when the catalog is empty.

test.describe("protocol catalog (dashboard explorer)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible({
      timeout: 30_000,
    });
  });

  test("lists catalog protocols that link to their research pages", async ({
    page,
  }) => {
    const links = page.locator('main a[href^="/protocols/"]');
    test.skip((await links.count()) < 1, "no catalog rows rendered (empty dataset)");
    const href = await links.first().getAttribute("href");
    expect(href).toMatch(/^\/protocols\/.+/);
  });

  test("sort, band and page-size controls drive server queries reflected in the URL", async ({
    page,
  }) => {
    // Sort by name (A-Z).
    await page.getByRole("combobox", { name: "Sort by" }).click();
    await page.getByRole("option", { name: "Name", exact: true }).click();
    await expect(page).toHaveURL(/sort=name/);

    // Filter to a single risk band.
    await page.getByRole("combobox", { name: "Filter by risk band" }).click();
    await page.getByRole("option", { name: "high", exact: true }).click();
    await expect(page).toHaveURL(/band=high/);

    // Change the server page size.
    await page.getByRole("combobox", { name: "Rows per page" }).click();
    await page.getByRole("option", { name: "100 / page", exact: true }).click();
    await expect(page).toHaveURL(/page_size=100/);
  });

  test("pagination advances to the next server page", async ({ page }) => {
    const next = page.getByRole("button", { name: "Next page" });
    // Only meaningful when the catalog spans more than one page.
    test.skip((await next.count()) === 0, "catalog fits on a single page");
    await next.click();
    await expect(page).toHaveURL(/[?&]page=2/);
  });
});
