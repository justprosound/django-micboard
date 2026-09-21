---
title: "ADR-013: Documentation Platform — Astro Starlight"
---
**Status:** Implemented
**Date:** 2026-09-21
**Deciders:** Project team
**Supersedes:** the MkDocs + Material + `mkdocstrings` documentation stack

## Context

The documentation site was built with MkDocs, the Material theme, and `mkdocstrings`, and
validated by the `build-docs` job in `.github/workflows/ci.yml`. The build worked, but three
problems had accumulated:

1. **Authoring ceiling.** MkDocs is a Python build tool with a theming layer, not a component
   framework. Material is already the best MkDocs theme available, so "stay on MkDocs and
   upgrade extensions" could not close the gap on component-driven pages, offline search
   quality, or theming control.
2. **A build that depended on Django.** The three `::: module` autodoc pages
   (`micboard.models`, `micboard.management`, `micboard.websockets.consumers`) tied the
   documentation build to the ability to load Django settings.
3. **Autodoc that did not document anything.** Because model classes are intentionally not
   re-exported from `micboard/models/__init__.py` (ADR-001, ADR-002), `::: micboard.models`
   rendered only the package docstring and a list of submodule names. The API reference
   pages carried almost no symbols.

A pre-migration inventory of the 76 Markdown pages found that all 76 were reachable from the
MkDocs `nav:` block, so no page was orphaned before the migration. The markup inventory was
also reassuringly small: one `!!!` admonition, no `pymdownx.tabbed` blocks, no Mermaid
diagrams, no snippets, no emoji shortcodes, and 138 file-relative `.md` links.

## Decision

Migrate the documentation site to **Astro Starlight**, and replace build-time Python autodoc
with a committed, pre-generated API reference.

### Candidate evaluation

| Candidate | Markdown reuse | Offline search | Versioning | Python autodoc | Verdict |
| --- | --- | --- | --- | --- | --- |
| **Astro Starlight** | Plain `.md` with light frontmatter | Built in (Pagefind) | None built in | Pre-build extraction | **Selected** |
| VitePress | Simplest migration | Built in (MiniSearch) | None | Pre-build extraction | Runner-up; weakest i18n |
| Docusaurus | MDX-leaning migration | Requires Algolia or a plugin | Best in class | Pre-build extraction | Fallback if versioning becomes required |
| Fumadocs | MDX-first | Built in | Via Next.js patterns | `fumadocs-python` (experimental) | Rejected: Next.js static-export weight |
| Nextra | MDX-first | Built in | Limited | None | Rejected |

Starlight wins on the axes that matter here: the existing Markdown is reusable almost as-is,
full-text search is offline and account-free, the output is plain static HTML/CSS/JS, and
i18n and RTL are first-class if they are ever needed.

### Implementation decisions

- **Pages stay in `docs/`.** Rather than moving 76 files into `src/content/docs/`, the `docs`
  content collection uses Astro's `glob` loader with `base: "./docs"` (see
  `src/content.config.ts`). The tree keeps rendering on GitHub, `git log --follow` history is
  preserved, and no path in `README.md`, `AGENTS.md`, or the issue tracker had to change.
- **Relative Markdown links are rewritten at build time.** `src/plugins/satteri-docs-links.mjs`
  converts links such as `../adr/011-introduce-eventbus.md` into the page URLs Starlight
  serves, mirroring Astro's slug generation. Authors keep writing file-relative links that
  also work when the file is read on GitHub, and no page content needed editing.
- **Frontmatter is the only per-page change.** `scripts/check_docs_frontmatter.py` lifted each
  page's leading `# Heading` into a `title` field (Starlight renders the title itself, so the
  duplicate heading is removed) and derived short `sidebar.label` values for the verbose SRED
  page titles. The script stays in the repository as a prek hook so new pages cannot be added
  without a title.
- **API reference is generated ahead of the build.** `scripts/generate_api_docs.py` walks a
  curated module list with Griffe's static analysis — no imports, no Django settings — and
  writes Markdown into `docs/api/reference/`. The output is committed, so `just docs` remains
  a single step, and `just docs-api` regenerates it. `prek` and CI run the generator in
  `--check` mode to catch drift.
- **Last-updated dates come from a route middleware.** Starlight's built-in `lastUpdated`
  support only inspects git history under `src/content/docs/`, so `src/routeData.ts` resolves
  the dates from a single `git log` pass over `docs/`. The CI job checks out full history for
  this reason.
- **Hosting is GitHub Pages, published from CI.** The repository's Pages source is the
  GitHub Actions workflow: `build-docs` uploads `site/` as a Pages artifact on `main` and the
  `deploy-docs` job publishes it to <https://justprosound.github.io/django-micboard/>. The
  deploy job opts out of the workflow-wide `cancel-in-progress` concurrency group, because
  Pages refuses concurrent deployments. `base: "/django-micboard"` in `astro.config.mjs`
  matches that project-pages sub-path, and `site/` remains the build output directory the CI
  job validates.
- **Brand tokens live in the theme.** `src/styles/micboard.css` mirrors the application
  palette from `micboard/static/micboard/css/theme.css`, and the header logo is imported
  directly from `micboard/static/micboard/logo.png` so the docs site and the application
  cannot drift on artwork. `scripts/sync-docs-assets.mjs` copies the canonical favicon into
  the generated `public/` directory at build time rather than committing a second copy.

## Consequences

### Positive

- The build no longer imports Django or reads `DJANGO_SETTINGS_MODULE`; it is hermetic and
  completes in a few seconds.
- The API reference now documents the model domains, the service layer, management commands,
  the WebSocket consumers, and the exception hierarchy — with `Args`/`Returns`/`Raises`
  sections and deep links to source lines — where the previous autodoc pages listed only
  module names.
- Search is offline, built into the site, and requires no external account.
- Page coverage, link integrity, search, brand rendering, and WCAG 2.1 AA compliance are all
  enforced in CI (`scripts/check_docs_coverage.py`, `scripts/check_docs_links.py`, and the
  Playwright suite in `tests/docs-e2e/`).

### Negative and accepted trade-offs

- **Inline autodoc is gone.** A `::: module` directive can no longer be dropped into a page;
  a module must be added to `PAGES` in `scripts/generate_api_docs.py` and the reference
  regenerated. This is the load-bearing cost of the migration and is accepted in exchange for
  a hermetic build. If the extractor ever falls short for a specific surface, the fallback is
  hand-authored Markdown for that surface plus links to source.
- **The toolchain now spans two ecosystems.** Node and npm become prerequisites alongside
  `uv`; once they are installed, `just install` installs both dependency trees. `just docs`
  fails with a clear message when npm is unavailable, and reinstalls the Node tree when the
  lockfile is newer than it.
- **No per-release versioning.** Starlight has no built-in versioning and the community
  `starlight-versions` plugin is experimental. We do not need per-release snapshots today. If
  that changes, the options are `starlight-versions` or a move to Docusaurus, whose
  `docusaurus docs:version` CLI is mature. Reopening the platform question for versioning
  alone is out of scope.
- **URLs changed.** The site moved off Read the Docs (`.readthedocs.yaml` and the exported
  `docs/requirements.txt` are deleted), and slugs are now generated by Astro, so
  `changelog/breaking-changes-v26.01/` is served as `changelog/breaking-changes-v2601/`.
- **i18n is available but unused.** Starlight supports localisation and RTL; no locale work is
  in scope, and none is configured.

## Compliance

- `just docs` builds the site; `just serve-docs` serves it on port 9000 with hot reload.
- `just docs-verify` runs the frontmatter, reference-freshness, page-coverage, and link checks.
- `just docs-e2e` runs the search, brand, and accessibility suite against the built site.
- The `build-docs` CI job runs all of the above and uploads `site/` as a Pages artifact on
  `main`; `deploy-docs` then publishes it to GitHub Pages.
- A merge performed with `GITHUB_TOKEN`, such as a bot-merged release pull request, does not
  raise the `push` event, so that commit publishes nothing. `deploy-docs` therefore also runs
  on `workflow_dispatch`; republish with `gh workflow run ci.yml --ref main`.
