import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

const pages = ["./", "./quickstart/", "./api/reference/models/"];

/**
 * Expressive Code marks horizontally scrollable code blocks as keyboard-focusable from a
 * debounced ResizeObserver callback. Axe has to run after that settles, or it reports the
 * blocks under "scrollable region must have keyboard access".
 */
async function waitForCodeBlockEnhancement(page: Page): Promise<void> {
  await page.waitForFunction(() =>
    [...document.querySelectorAll(".expressive-code pre")].every(
      (block) => block.scrollWidth <= block.clientWidth || block.hasAttribute("tabindex"),
    ),
  );
}

for (const path of pages) {
  for (const theme of ["light", "dark"] as const) {
    test(`${path} has no WCAG 2.1 AA violations in the ${theme} theme`, async ({ page }) => {
      await page.addInitScript(
        (value) => window.localStorage.setItem("starlight-theme", value),
        theme,
      );
      await page.goto(path);
      await waitForCodeBlockEnhancement(page);

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      expect(results.violations).toEqual([]);
    });
  }
}

test("the first tab stop is a visible skip link", async ({ page }) => {
  await page.goto("./");

  await page.keyboard.press("Tab");
  const focused = page.locator(":focus");
  await expect(focused).toHaveText(/skip to content/i);
  await expect(focused).toBeVisible();
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("animations are suppressed when the visitor asks for less motion", async ({ page }) => {
    await page.goto("./");

    const duration = await page.evaluate(() => {
      const element = document.querySelector("a");
      return element ? getComputedStyle(element).transitionDuration : "";
    });

    expect(Number.parseFloat(duration)).toBeLessThan(0.05);
  });
});
