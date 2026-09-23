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
      editLink: { baseUrl: `${repository}/edit/main/` },
      lastUpdated: true,
      routeMiddleware: "./src/routeData.ts",
      credits: false,
      social: [{ icon: "github", label: "GitHub", href: repository }],
      sidebar: [
        {
          label: "Getting Started",
          items: [
            { label: "Overview", link: "/" },
            "quickstart",
            "installation",
            "configuration",
          ],
        },
        {
          label: "User Guide",
          items: [{ autogenerate: { directory: "guides" } }],
        },
        {
          label: "Deployment",
          items: ["demo-deployment"],
        },
        {
          label: "Multi-Tenancy",
          items: ["multitenancy", "multitenancy-quickref"],
        },
        {
          label: "Shure Integration",
          items: [
            "shure-integration",
            "integration/discovery-workflow",
            "integration/integration-references",
            "guides/shure-troubleshooting",
          ],
        },
        {
          label: "API Reference",
          items: [
            "api/models",
            "api/endpoints",
            "api/websocket",
            "api/management",
            "api/serializers",
            "api/views",
            {
              label: "Generated from source",
              items: [{ autogenerate: { directory: "api/reference" } }],
            },
          ],
        },
        {
          label: "Architecture & Development",
          items: [
            "architecture",
            "design",
            "development",
            "development/architecture",
            "development/api-reference",
            "development/context",
            "development/tasks",
            "development/modern-tooling",
            "development/dependency-management",
            "plugin-development",
          ],
        },
        {
          label: "Agent Guidance",
          items: ["agents/domain", "agents/issue-tracker", "agents/triage-labels"],
        },
        {
          label: "Architecture Decisions",
          items: [{ autogenerate: { directory: "adr" } }],
        },
        {
          label: "Product Requirements",
          items: [{ autogenerate: { directory: "prd" } }],
        },
        {
          label: "SRED 2026",
          items: [{ autogenerate: { directory: "sred/2026" } }],
        },
        {
          label: "About",
          items: ["changelog", "changelog/breaking-changes-v2601"],
        },
      ],
    }),
  ],
});
