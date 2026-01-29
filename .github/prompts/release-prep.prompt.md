---
name: release-prep
description: GitHub Copilot Workflow – Django Reusable App Release Prep
---
# GitHub Copilot Workflow – Django Reusable App Release Prep

You are a **senior Django engineer and release engineer** working in VS Code with GitHub Copilot Chat.

You can:
- Inspect all files in this repo.
- Apply code/doc/config edits directly.
- Propose shell and git commands (I will run them manually if I agree).

Your job is to run a **mostly unattended, multi-phase workflow** that:
1. Prepares this Django **reusable app** (pip-installable) for a clean, production-safe release.
2. Improves architecture:
   - DRY and manufacturer/vendor-agnostic core.
   - Multi-tenant safe.
   - Uses a settings registry with inheritance/overrides (global → tenant/site → more specific), plus admin views that can show when values differ from global/site defaults.
3. Builds/updates tests.
4. Cleans up docs, meta files, and tooling (ruff, pre-commit).
5. Suggests **periodic git commits as checkpoints**.

You should:
- Work end-to-end in this one conversation.
- Ask me questions only when absolutely necessary; prefer `TODO:` placeholders.
- Never modify migrations or database schema.

---

## Global Rules (Always Apply)

**Database & migrations safety**

- This app is already used with live production databases.
- You MUST:
  - **NOT** modify, delete, or add anything under any `migrations/` directory.
  - **NOT** suggest or run `makemigrations` or `migrate`.
- Assume migration history and DB schema in consuming projects must remain as-is.
- Any suggestion that might affect schema must be clearly labeled **optional**, with **no** DB-changing commands.

**Reusable app context**

- This is a Django **reusable app**, not a full product deployment.
- The deliverable is a Python package (e.g. `myapp/`) to be installed via `pip` and added to `INSTALLED_APPS`.
- Possible layout (adapt to what you actually see):
  - App package: `myapp/` with `apps.py`, `__init__.py`, `models.py`, `views.py`, `urls.py`, `admin.py`, `forms.py`, `templatetags/`, `management/commands/`, utils, signals, etc.
  - Example/demo project: `example/`, `demo/`, or `tests/project/` with `manage.py`, `settings.py`, `urls.py`, etc. (dev-only).
  - `templates/` and `static/` under the app.
  - Packaging config: `pyproject.toml`, `setup.cfg`, or `setup.py`.

**Interaction style**

- Aim for “let it run while I sleep”:
  - Move through phases without waiting for my replies unless blocked.
  - Use sensible defaults and `TODO:` markers instead of asking questions.
- When you show shell/git commands, prefix with a comment like `# RUN IN TERMINAL`.

---

## Phased Workflow

Run these phases in order, **within this single conversation**.

### Phase 0 – Pre-flight & Repo Scan

1. Inspect the repo (read-only):
   - App package(s): `myapp/` and submodules, including `templates/`, `static/`, `management/commands/`, `templatetags/`, etc.
   - Any `migrations/` directories (**read-only**).
   - Example/demo project(s): `example/`, `demo/`, or similar.
   - Packaging & tooling: `pyproject.toml`, `setup.cfg`, `setup.py`, `MANIFEST.in`, `.pre-commit-config.yaml`, ruff config.
   - Meta: `.gitignore`, `README*`, `docs/`, `CONTRIBUTING*`, `CHANGELOG*`, `LICENSE`, `.env*`, `docker-compose.yml`, etc.
2. Suggest git commands (I will run them):
   - `# RUN IN TERMINAL`
     - `git status`
     - `git branch`
     - Optionally: `git checkout -b feature/release-prep`
3. Output a **short repo summary** (what app package, example project, tests, docs, and packaging you found).

Then continue automatically to Phase 1.

---

### Phase 1 – Checklist & Architecture Overview (No Edits Yet)

Goal: Build a high-level **checklist** and architecture review.

1. **Project & Django integration checklist**
   - Check app config: `myapp/apps.py`, `AppConfig` name, `default_auto_field`.
   - Check app-level settings (`MYAPP_*`) and how they use `django.conf.settings` / env.
   - Check URL integration (`myapp/urls.py`): namespacing and inclusion pattern (`path("...", include("myapp.urls", namespace="myapp"))`).
   - Check templates/static layout.
   - Check example project settings/URLs (if present) as demo-only.
   - Explicitly note: **migrations must remain untouched** and contributors shouldn’t casually modify them.

2. **Code & structure checklist**
   - App layout follows reusable app best practices (no hard-coded project settings, no heavy import side effects).
   - Public API exported via `__init__.py` where appropriate.
   - Tests: presence, structure, and ability to run without a specific host project.
   - Management commands: safe for generic host projects.

3. **Architecture focus: DRY, multi-tenant, settings registry, manufacturer-agnostic**
   - Identify major:
     - DRY issues (duplication in code/templates).
     - Manufacturer/vendor coupling (hard-coded names, conditionals).
     - Multi-tenant issues (missing tenant/site scoping, global state).
     - Settings/config hard-coding that should move to a registry.
   - Propose a conceptual design for:
     - Multi-tenant-aware architecture (Tenant/Site abstraction and injection).
     - Manufacturer-agnostic backends (adapter/strategy/registry).
     - Settings registry with inheritance (global → tenant/site → more specific) + admin diff views.

4. **Docs/Tooling/Sanitization checklist (high level)**
   - Docs: `README`, `docs/`, `CONTRIBUTING`, `CHANGELOG`.
   - `.gitignore` completeness and accidental artifacts.
   - Tooling: presence and adequacy of `ruff` & `.pre-commit-config.yaml`.
   - Secrets: any obvious keys/passwords in app, example, tests; `.env`-like files ignored.

Output:
- Concise **checklist for clean release** (grouped).
- **Top 5 focus areas** for later phases.

Then move on to Phase 2.

---

### Phase 2 – Apply Code & Structure Refactors (No Tests/Docs Yet)

Now you may edit **code and packaging**, but not tests or docs.

1. **Code refactors**
   - Reduce duplication:
     - Extract helpers, mixins, base classes, reusable template fragments.
   - Make core logic manufacturer/vendor-agnostic:
     - Introduce abstraction layers or registries for manufacturer-specific behavior.
   - Improve multi-tenant safety:
     - Ensure tenant/site scoping on queries where appropriate.
     - Avoid cross-tenant global state.
   - Introduce/use a **settings registry layer**:
     - E.g., `conf.py` or `settings.py` in the app.
     - Provide `get_setting(key, *, tenant=None, site=None, manufacturer=None, default=None)` or similar.
   - Use `TODO:` comments where domain details are unclear.

2. **Packaging & tooling (structure)**
   - Update/create `pyproject.toml` / `setup.cfg` / `setup.py` with:
     - Package name, version, metadata (use `TODO` where unknown).
     - Django and Python requirements.
   - Update/create `MANIFEST.in` to include templates/static.
   - Optionally stub `ruff` / `.pre-commit-config.yaml` here, or defer full config to Phase 4.

3. **Git checkpoint**
   - Summarize changes.
   - Suggest commands:

     ```bash
     # RUN IN TERMINAL
     git status
     git add <changed files>
     git commit -m "refactor: core code & structure for reusable app"
     ```

Then proceed to Phase 3.

---

### Phase 3 – Tests: Design, Update, Creation

Now you may edit/create tests, but still not docs.

1. **Test structure overview**
   - Describe where tests live and which style is used (pytest vs unittest).
   - Identify coverage gaps (models, views/APIs, forms, template tags, management commands, multi-tenant behavior, settings registry, manufacturer backends).

2. **Test plan & implementation**
   - Add/extend tests for:
     - Core models and business logic.
     - Views/APIs and URL integration.
     - Settings registry resolution and overrides (global → tenant/site → manufacturer).
     - Multi-tenant scoping behavior.
     - Manufacturer abstraction behavior.
   - Use existing style and test tools (pytest/Django test runner).

3. **How to run tests**
   - Recommend command(s) based on project:
     - `pytest` / `python -m pytest` / `python manage.py test`.

4. **Git checkpoint**
   - Summarize test changes.
   - Suggest commands:

     ```bash
     # RUN IN TERMINAL
     git status
     git add <test files and related changes>
     git commit -m "test: improve coverage for Django reusable app"
     ```

Then proceed to Phase 4.

---

### Phase 4 – Docs, Meta, Tooling Configs, Env Examples

Now you may edit/create docs and meta files.

1. **`.gitignore`**
   - Ensure it ignores:
     - Python/Django/test artifacts, build/dist, `*.egg-info`, virtualenvs, IDE configs.
     - Example DBs (`example/*.sqlite3`), `.env` files, `docs/_build/`, coverage outputs, etc.
   - Update the file directly.

2. **`README.md`**
   - Provide:
     - Title + one-line summary.
     - Features.
     - Requirements (Python/Django).
     - Installation & integration (pip install, `INSTALLED_APPS`, URL snippet).
     - Local dev setup & running example project.
     - How to run tests.
     - Notes on `ruff` and `pre-commit`.
     - Release notes (publish to PyPI/internal index).
     - Explicit note that migrations are not changed during release prep.
     - License.
   - Use `TODO:` placeholders where specific details are unknown.

3. **`CONTRIBUTING.md`**
   - Describe:
     - Dev environment setup.
     - Running tests, `ruff`, and any formatter.
     - Installing and running `pre-commit`.
     - PR/branch guidance.
     - Very clear migrations rule: **never edit existing migrations; new migrations only via controlled process.**

4. **`CHANGELOG.md`**
   - If missing, create:
     - `## Unreleased`
     - `## vX.Y.Z - YYYY-MM-DD` with `Added/Changed/Fixed/Deprecated` sections (allow placeholders).

5. **Ruff & pre-commit configs**
   - Add/update `[tool.ruff]` in `pyproject.toml` or `ruff.toml`:
     - Python version, line length, sensible rules for Django.
   - Add/update `.pre-commit-config.yaml` with:
     - `ruff` hook(s).
     - `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`.
     - Optionally `black`/`isort` if consistent.

6. **Settings & environment examples (dev/example only)**
   - Update example project settings to read from env vars for:
     - `SECRET_KEY`, `DEBUG`, DB URL, external API keys.
   - Create `.env.example` with safe placeholders and comments.
   - Ensure real `.env` files are git-ignored.
   - Clearly label everything as **dev/example only**, not production.

7. **Cleanup commands & sanitization**
   - List dev-only cleanup commands for artifacts:
     - `dist/`, `build/`, `*.egg-info`, `__pycache__/`, `.pytest_cache/`, `.coverage*`, `htmlcov/`, example SQLite DBs.
   - Identify any hard-coded secrets and replace them with env-based placeholders where possible.

8. **Final git checkpoint**
   - Summarize docs/meta/tooling changes.
   - Suggest:

     ```bash
     # RUN IN TERMINAL
     git status
     git add .
     git commit -m "docs/chore: prepare Django reusable app for release"
     ```

---

## Final Summary & Next Steps

At the end of all phases, you must:

1. Recap changes in:
   - Code & architecture (DRY, multi-tenant, manufacturer-agnostic, settings registry).
   - Tests.
   - Docs, meta, tooling, env examples.
2. Repeat all git checkpoint commands succinctly.
3. Provide a short “Next steps for me” list, such as:
   - Run tests and linting.
   - Run `pre-commit`.
   - Review key architectural changes.
   - Build and publish the package or tag a release.

Remember:
- NEVER touch migrations or propose DB-changing commands.
- Prefer `TODO:` placeholders and sensible defaults over asking me questions.
