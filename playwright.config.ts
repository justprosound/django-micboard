import { defineConfig, devices } from "@playwright/test";

// The suite drives the built site through `astro preview`, because Pagefind's search index
// only exists after a production build. Port 9000 matches the local documentation server.

const baseURL = "http://localhost:9000/django-micboard/";

export default defineConfig({
  testDir: "./tests/docs-e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [["github"], ["list"], ["html", { outputFolder: "playwright-report", open: "never" }]]
    : "list",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run docs:preview",
    url: baseURL,
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
});
