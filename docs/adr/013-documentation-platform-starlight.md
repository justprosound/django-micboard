---
title: "ADR-013: Documentation platform is Astro Starlight"
description: "How the documentation site is built and why pages stay in docs/."
type: explanation
audience: developer
---

## Context

The site needs offline full-text search, theming control and a build that does not import Django. Python autodoc pages that load Django settings tie the build to the host configuration, and model classes that are deliberately not re-exported from `micboard/models/__init__.py` render as near-empty pages.

## Decision

The site is built with [Astro Starlight](https://starlight.astro.build/) and hosted on GitHub Pages.

- **Pages stay in `docs/`.** The content collection in `src/content.config.ts` reads `./docs`, so the tree renders on GitHub and paths in the README and issue tracker keep working.
- **Relative Markdown links are rewritten at build time** by `src/plugins/satteri-docs-links.mjs`, so authors write file-relative links that also work on GitHub.
- **Frontmatter carries `title`, `type` and `audience`.** `type` is one of the four Diátaxis types and `audience` says who the page is for; the content schema rejects a page without them. `scripts/check_docs_frontmatter.py` keeps each page's title in frontmatter.
- **The Python API reference is generated ahead of the build** by `scripts/generate_api_docs.py`, which reads the source statically with Griffe and writes Markdown into `docs/api/reference/`. The output is committed, `just docs-api` regenerates it, and CI runs the generator in `--check` mode.
- **"Last updated" dates come from git** through `src/routeData.ts`, because Starlight only inspects `src/content/docs/`. CI therefore checks out full history.
- **Brand tokens live in the theme** (`src/styles/micboard.css`), and the logo is imported from the application's static assets so the two cannot drift.
- **CI publishes the site.** The `build-docs` job validates and uploads `site/`, and `deploy-docs` publishes it to GitHub Pages on `main`. A merge made with `GITHUB_TOKEN` does not raise a `push` event, so `deploy-docs` also runs on `workflow_dispatch`.

## Consequences

The build is hermetic and fast, and search needs no external account. A module appears in the API reference only after it is added to `PAGES` in `scripts/generate_api_docs.py`. The toolchain spans `uv` and Node. Starlight has no built-in per-release versioning, so the site documents the current release only.

Checks: `just docs` builds, `just docs-verify` runs frontmatter, reference-freshness, page-coverage and link checks, and `just docs-e2e` runs the search, brand and accessibility suite.
