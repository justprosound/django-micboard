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

/**
 * Starlight's header search button is named "Search" by `aria-label` and shows a `Ctrl K` shortcut
 * hint, which it also exposes through `aria-keyshortcuts`. Since 4.14, axe counts that hint as part
 * of the visible label and reports `label-content-name-mismatch`. Under WCAG 2.5.3 the hint is
 * symbolic text, not the label, so Starlight declined to change the markup
 * (https://github.com/withastro/starlight/issues/4260). This allowance covers that rule on that
 * one button only; every other rule still runs on it.
 */
const knownFalsePositives = [
  { rule: "label-content-name-mismatch", target: 'button[data-open-modal=""]' },
];

type Violations = Awaited<ReturnType<AxeBuilder["analyze"]>>["violations"];

function withoutKnownFalsePositives(violations: Violations): Violations {
  return violations
    .map((violation) => ({
      ...violation,
      nodes: violation.nodes.filter(
        (node) =>
          !knownFalsePositives.some(
            ({ rule, target }) =>
              violation.id === rule && node.target.length === 1 && node.target[0] === target,
          ),
      ),
    }))
    .filter((violation) => violation.nodes.length > 0);
}

const searchButton = 'button[data-open-modal=""]';

/** Builds the minimal violation shape the filter reads, so the cases below stay readable. */
function violation(id: string, targets: string[]): Violations[number] {
  return {
    id,
    nodes: targets.map((target) => ({ target: [target] })),
  } as unknown as Violations[number];
}

test.describe("known false positive filter", () => {
  /** The allowed rule on the search button is the only thing the filter may drop. */
  test("drops the allowed rule on the search button", () => {
    expect(
      withoutKnownFalsePositives([violation("label-content-name-mismatch", [searchButton])]),
    ).toEqual([]);
  });

  /** The same rule must still fail on any other element. */
  test("keeps the allowed rule on other targets", () => {
    const other = violation("label-content-name-mismatch", ["a.site-title"]);
    expect(withoutKnownFalsePositives([other])).toEqual([other]);
  });

  /** Every other rule must still fail on the search button. */
  test("keeps other rules on the search button", () => {
    const other = violation("color-contrast", [searchButton]);
    expect(withoutKnownFalsePositives([other])).toEqual([other]);
  });

  /** A violation that also covers other nodes keeps those nodes and still fails. */
  test("keeps the other nodes of a mixed violation", () => {
    expect(
      withoutKnownFalsePositives([
        violation("label-content-name-mismatch", [searchButton, "a.site-title"]),
      ]),
    ).toEqual([violation("label-content-name-mismatch", ["a.site-title"])]);
  });
});

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

      expect(withoutKnownFalsePositives(results.violations)).toEqual([]);
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
