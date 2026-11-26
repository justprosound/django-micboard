// @ts-check
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";

import { satteri } from "@astrojs/markdown-satteri";

import docsLinks from "./src/plugins/satteri-docs-links.mjs";
import taskListLabels from "./src/plugins/satteri-task-list-labels.mjs";

const repository = "https://github.com/justprosound/django-micboard";
const base = "/django-micboard";

export default defineConfig({
  // Project pages are served from a repository sub-path; `base` keeps every generated
  // asset and navigation URL correct there and in local development.
  site: "https://justprosound.github.io",
  base,
  // `site/` is the directory the CI documentation job validates and uploads.
  outDir: "./site",
  // Pages that were merged into another keep their old URL. Pages with no successor are not
  // listed: git history is their archive.
  redirects: {
    "/multitenancy-quickref": `${base}/multitenancy-setup/`,
    "/design": `${base}/architecture/`,
    "/development/architecture": `${base}/architecture/`,
    "/guides/settings-system-summary": `${base}/guides/settings-management/`,
    "/api/serializers": `${base}/api/endpoints/`,
    "/api/views": `${base}/api/endpoints/`,
    "/changelog": `${repository}/blob/main/CHANGELOG.md`,
  },
  markdown: {
    processor: satteri({
      mdastPlugins: [docsLinks({ docsDir: "docs", base })],
      hastPlugins: [taskListLabels()],
    }),
  },
  integrations: [
    starlight({
      title: "django-micboard",
      // Django template snippets are highlighted with Shiki's Django/Jinja grammar.
      expressiveCode: { shiki: { langAlias: { django: "django-html" } } },
      description:
        "Real-time multi-manufacturer wireless microphone monitoring for Django.",
      // Consumed straight from the app's canonical static assets so the docs site and the
      // application can never drift on logo artwork.
      logo: {
        src: "./micboard/static/micboard/logo.png",
        alt: "django-micboard",
      },
      favicon: "/favicon.png",
      customCss: ["./src/styles/micboard.css"],
      components: { Search: "./src/components/Search.astro" },
      editLink: { baseUrl: `${repository}/edit/main/` },
      lastUpdated: true,
      routeMiddleware: "./src/routeData.ts",
      credits: false,
      social: [{ icon: "github", label: "GitHub", href: repository }],
      // The four Diátaxis types. A page declares its type in frontmatter, and the sidebar
      // lists it under the matching section.
      sidebar: [
        { label: "Overview", link: "/" },
        {
          label: "Tutorials",
          items: ["quickstart"],
        },
        {
          label: "How-to guides",
          items: [
            // Staff pages first, then developer pages.
            "guides/admin-interface",
            "guides/monitoring",
            "guides/settings-admin-guide",
            "guides/band-plan-auto-population",
            "guides/resolve-regulatory-coverage",
            "integration/review-discovery-queue",
            "guides/shure-troubleshooting",
            "demo-deployment",
            "installation",
            "shure-integration",
            "multitenancy-setup",
            "guides/realtime-updates",
            "guides/settings-integration",
            "guides/performer-quickref",
            "plugin-development",
            "development",
            "development/modern-tooling",
            "development/dependency-management",
            "agents/domain",
            "agents/issue-tracker",
          ],
        },
        {
          label: "Reference",
          items: [
            "guides/settings-quick-reference",
            "configuration",
            "api/endpoints",
            "api/websocket",
            "api/management",
            "api/models",
            {
              label: "Generated from source",
              items: [{ autogenerate: { directory: "api/reference" } }],
            },
            "development/api-reference",
            "integration/integration-references",
            "guides/api-band-plan-detection",
            "guides/settings-management",
            "development/context",
            "agents/triage-labels",
          ],
        },
        {
          label: "Explanation",
          items: [
            "integration/discovery-workflow",
            "guides/regulatory-coverage-monitoring",
            "architecture",
            "multitenancy",
            "guides/performer-assignment-architecture",
            "demo-deployment-design",
            {
              label: "Architecture decisions",
              items: [{ autogenerate: { directory: "adr" } }],
            },
          ],
        },
      ],
    }),
  ],
});
