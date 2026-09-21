import { expect, test } from "@playwright/test";

test("the header renders the application's canonical logo", async ({ page }) => {
  await page.goto("./");

  const logo = page.locator(".site-title img").first();
  await expect(logo).toBeVisible();
  await expect(logo).toHaveAttribute("src", /logo/);
  await expect(logo).toHaveAttribute("alt", /django-micboard/i);
});

for (const theme of ["light", "dark"] as const) {
  test(`brand accent tokens are applied in the ${theme} theme`, async ({ page }) => {
    await page.addInitScript(
      (value) => window.localStorage.setItem("starlight-theme", value),
      theme,
    );
    await page.goto("./");

    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    const value = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--sl-color-accent").trim(),
    );

    // Brand blue in light mode, its lightened variant on dark surfaces.
    expect(value.toLowerCase()).toBe(theme === "light" ? "#006494" : "#0079b3");
  });
}

test("the theme toggle switches between light and dark", async ({ page }) => {
  await page.goto("./");

  const toggle = page.getByLabel(/theme/i).first();
  await toggle.selectOption("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await toggle.selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});
