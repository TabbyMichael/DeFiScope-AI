import { expect, test } from "@playwright/test";

const BANDS = ["low", "moderate", "elevated", "high", "unknown"] as const;

// Each row's last cell holds the RiskBadge: "<band><optional score>". Parse the
// leading band token so we can assert filters without coupling to score values.
function bandOf(text: string): string | undefined {
  const trimmed = text.trim();
  return BANDS.find((b) => trimmed.startsWith(b));
}

test.describe("protocol table", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible({
      timeout: 30_000,
    });
  });

  test("sorts protocols by name (asc then desc)", async ({ page }) => {
    const names = page.locator('main table tbody a[href^="/protocols/"]');
    test.skip((await names.count()) < 2, "need at least two protocols to sort");

    // Column defaults to TVL desc; clicking "Protocol" switches to name asc.
    await page.getByRole("button", { name: "Protocol" }).click();
    const asc = await names.allTextContents();
    expect(asc).toEqual([...asc].sort((a, b) => a.localeCompare(b)));

    // A second click flips the same column to desc.
    await page.getByRole("button", { name: "Protocol" }).click();
    const desc = await names.allTextContents();
    expect(desc).toEqual([...asc].reverse());
  });

  test("filters protocols by risk band", async ({ page }) => {
    const badges = page.locator("main table tbody tr td:last-child");
    const total = await badges.count();
    test.skip(total < 1, "no protocols rendered yet (empty dataset)");

    const initialBands = (await badges.allTextContents()).map(bandOf);
    const present = Array.from(new Set(initialBands.filter(Boolean))) as string[];
    test.skip(present.length === 0, "no protocol has a resolvable risk band");

    // Pick a band that exists so the filtered result is guaranteed non-empty,
    // then assert every surviving row carries that band.
    const target = present[0];
    const expectedRows = initialBands.filter((b) => b === target).length;

    // The shadcn Select trigger exposes role="combobox" with the label set on
    // the trigger (aria-label), so name it rather than looking for a button.
    await page.getByRole("combobox", { name: "Filter by risk band" }).click();
    await page.getByRole("option", { name: target, exact: true }).click();

    await expect(
      page.getByRole("combobox", { name: "Filter by risk band" }),
    ).toContainText(target);
    const filtered = page.locator("main table tbody tr td:last-child");
    await expect(filtered).toHaveCount(expectedRows);
    for (const text of await filtered.allTextContents()) {
      expect(bandOf(text)).toBe(target);
    }
  });
});
