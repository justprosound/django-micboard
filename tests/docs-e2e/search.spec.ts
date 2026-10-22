import { expect, test } from "@playwright/test";

test("search exposes its visible shortcut and opens from the keyboard", async ({ page }) => {
  await page.goto("./");
  const button = page.locator("site-search button[data-open-modal]");
  const shortcut = (await button.locator("kbd").first().innerText()).replace(/\s+/g, " ").trim();

  await expect(button).toHaveAccessibleName(`Search ${shortcut}`);
  await page.keyboard.press("Control+k");

  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog").getByPlaceholder(/search/i)).toBeFocused();
});

// Pagefind ships the search index with the site, so this also proves search works without
// an external service or account.
test("offline search finds a page by a term from its body", async ({ page }) => {
  await page.goto("./");

  await page.getByRole("button", { name: /search/i }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByPlaceholder(/search/i).fill("band plan");

  const result = dialog.getByRole("link", { name: /band plan/i }).first();
  await expect(result).toBeVisible();
  await result.click();
  await expect(page).toHaveURL(/band-plan/);
});
