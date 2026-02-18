# Modern Python Tooling Guide

This document describes the modern development tools integrated into django-micboard.

## Overview

We've adopted industry-standard tooling from the django-gt-template to improve developer experience and code quality:

1. **just** - Modern command runner (replaces Make)
2. **django-lifecycle** - Declarative model lifecycle hooks
3. **pre-commit hooks** - Automated code quality checks
4. **commitlint** - Conventional commit enforcement
5. **editorconfig** - Consistent code formatting across editors

---

## 1. Justfile - Task Automation

`just` is a modern alternative to `make` with better syntax and cross-platform support.

### Installation

```bash
# macOS
brew install just

# Linux
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin

# Or use cargo
cargo install just
```

### Common Commands

```bash
# List all available commands
just

# Install all dependencies
just install

# Run linters and formatters
just lint

# Run tests
just test

# Run tests with coverage report
just test-coverage

# Quick validation before commit
just quick-check

# Run Django development server
just run

# Run device discovery
just discover shure

# Build documentation
just docs
just serve-docs

# Clean build artifacts
just clean

# Run full CI pipeline locally
just ci
```

### Key Features

- **Parallel execution**: Commands run efficiently
- **Environment variables**: Automatic `.env` loading with `set dotenv-load`
- **Cross-platform**: Works on macOS, Linux, and Windows
- **Tab completion**: Available for most shells
- **Clear syntax**: No tab/space issues like Make

---

## 2. django-lifecycle - Model Lifecycle Hooks

**Status**: ✅ Integrated into `WirelessChassis` model

### What It Does

Replaces manual lifecycle management (`HardwareLifecycleManager`) with declarative hooks that:
- **Cannot be bypassed** - Hooks fire automatically on save
- **Enforce state machine** - Invalid transitions raise `ValueError`
- **Auto-manage timestamps** - `last_online_at`, `last_offline_at`, `total_uptime_minutes`
- **Audit logging** - Every status change logged automatically
- **Broadcast events** - Real-time updates via `BroadcastService`

### Example Usage

```python
# OLD WAY (manual lifecycle manager)
from micboard.services.hardware_lifecycle import get_lifecycle_manager

lifecycle = get_lifecycle_manager("shure")
lifecycle.mark_online(chassis)

# NEW WAY (automatic hooks)
chassis.status = "online"
chassis.save()  # Hooks fire automatically:
                # - Validates transition
                # - Updates timestamps
                # - Logs to audit
                # - Broadcasts event
```

### Hooks Implemented

1. **`validate_status_transition`** (`BEFORE_SAVE`)
   - Validates state machine transitions
   - Raises `ValueError` for invalid transitions
   - Enforces business rules

2. **`on_status_online`** (`AFTER_UPDATE`)
   - Sets `last_online_at` timestamp
   - Sets `is_online = True`

3. **`on_status_offline`** (`AFTER_UPDATE`)
   - Sets `last_offline_at` timestamp
   - Sets `is_online = False`
   - Calculates `total_uptime_minutes`

4. **`log_status_change_to_audit`** (`AFTER_UPDATE`)
   - Creates audit log entry
   - Tracks old→new status

5. **`broadcast_status_change`** (`AFTER_UPDATE`)
   - Broadcasts to real-time subscribers
   - Enables live dashboard updates

### State Machine

```
discovered → provisioning → online ⟺ degraded
                 ↓            ↓         ↓
            offline ← - - - - ┘         ↓
                 ↓                      ↓
            maintenance ← - - - - - - -┘
                 ↓
             retired (terminal)
```

### Testing

Run lifecycle hook tests:

```bash
just test-file tests/test_lifecycle_hooks.py
pytest tests/test_lifecycle_hooks.py -vv
```

---

## 3. Pre-commit Hooks

Automated code quality checks that run before each commit.

### Installation

```bash
# Install hooks
just install

# Or manually
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

### What Gets Checked

1. **Ruff format** - Auto-format Python code
2. **Ruff check** - Lint and auto-fix issues
3. **django-upgrade** - Upgrade to Django 5.1+ patterns
4. **Bandit** - Security vulnerability scanning
5. **mypy** - Type checking
6. **yamllint** - YAML validation
7. **commitlint** - Conventional commit messages
8. **Common checks** - Trailing whitespace, EOF, large files, etc.

### Running Manually

```bash
# Run all hooks on all files
just pre-commit

# Run specific hook
pre-commit run ruff-format --all-files

# Skip hooks for emergency commits (not recommended)
git commit --no-verify -m "..."
```

---

## 4. Commitlint - Conventional Commits

Enforces structured commit messages for better changelog generation and semantic versioning.

### Format

```
type(scope): subject

body (optional)

footer (optional)
```

### Valid Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `build`: Build system or external dependencies
- `ci`: CI configuration changes
- `chore`: Other changes (e.g., dependency updates)
- `revert`: Revert previous commit

### Valid Scopes (Optional)

- `services` - Service layer changes
- `models` - Model changes
- `views` - View changes
- `admin` - Admin interface changes
- `tasks` - Background task changes
- `api` - API changes
- `integrations` - Manufacturer integrations
- `discovery` - Discovery system
- `monitoring` - Monitoring features
- `lifecycle` - Lifecycle management
- `multitenancy` - Multi-tenant features
- `websockets` - WebSocket functionality
- `deps` - Dependency updates
- `config` - Configuration changes

### Examples

```bash
# Good commits
git commit -m "feat(lifecycle): add django-lifecycle hooks to WirelessChassis"
git commit -m "fix(discovery): handle timeout errors in API polling"
git commit -m "docs: update README with Justfile usage"
git commit -m "refactor(services): remove HardwareLifecycleManager shim"

# Bad commits (will be rejected)
git commit -m "updated stuff"              # No type
git commit -m "FEAT: new feature"          # Uppercase type
git commit -m "feat(unknown): thing"       # Invalid scope
git commit -m "feat: this is a very long subject line that exceeds the 72 character limit"
```

---

## 5. EditorConfig

Ensures consistent code formatting across all editors and IDEs.

### Supported Editors

- VS Code
- PyCharm / IntelliJ
- Vim / Neovim
- Emacs
- Sublime Text
- Atom

### Settings

```ini
# Python files
indent_style = space
indent_size = 4
max_line_length = 100

# YAML/JSON
indent_size = 2

# Markdown
trim_trailing_whitespace = false
```

Most editors auto-detect and apply these settings.

---

## Benefits

### For Developers

- **Faster onboarding** - `just install` sets up everything
- **Consistent workflow** - Same commands across all platforms
- **Fewer mistakes** - Pre-commit catches issues before CI
- **Better commits** - Commitlint ensures quality messages
- **Auto-formatting** - No debates about style

### For Maintainers

- **Better git history** - Conventional commits enable auto-changelog
- **Semantic versioning** - Types drive version bumps
- **Fewer review comments** - Linting catches common issues
- **Safer refactoring** - Type checking catches errors

### For CI/CD

- **Faster builds** - Fewer lint/test failures
- **Cleaner logs** - Consistent formatting
- **Automated releases** - Conventional commits enable auto-release

---

## Migration from Old Patterns

### Before (manual commands)

```bash
# Old way - manual commands (**FORBIDDEN – see policy below**)
# python -m venv .venv
# source .venv/bin/activate
# pip install -e ".[dev,all]"
pytest
ruff format .
ruff check --fix .
mypy micboard
python manage.py runserver
```

### After (just/uv commands — **MANDATORY**)

```bash
# New way - just commands (with uv for environment & install)
just install
just test
just lint
just run
```

> **Note:** All environment and dependency management must use `uv` (see top of README, AGENTS.md, and CONTRIBUTING.md for enforcement policy). Any reference to pip, venv, poetry, or pipx should be escalated to maintainers and corrected immediately.

### Code Changes

```python
# OLD: Manual lifecycle management
from micboard.services.hardware_lifecycle import get_lifecycle_manager

lifecycle = get_lifecycle_manager(manufacturer.code)
lifecycle.mark_online(chassis, health_data=health_data)

# NEW: Declarative hooks (django-lifecycle)
chassis.status = "online"
chassis.save()  # Hooks fire automatically
```

---

## Troubleshooting

### Just command not found

```bash
# Install just
brew install just  # macOS
# or see: https://just.systems/man/en/chapter_4.html
```

### Pre-commit hooks failing

```bash
# Update hooks
pre-commit autoupdate

# Clear cache
pre-commit clean

# Reinstall
pre-commit uninstall
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

### Commitlint errors

```bash
# Check commit message format
echo "feat(services): add new feature" | npx commitlint

# View allowed types/scopes
cat .commitlintrc.yaml
```

### django-lifecycle not working

```bash
# Ensure dependency installed
pip install django-lifecycle>=1.2.4

# Check model has LifecycleModelMixin
# Should see: class WirelessChassis(LifecycleModelMixin, models.Model):
```

---

## Next Steps

### Agent & Research Workflow Policy

- When you need to search programming or package documentation as a developer or agent, always use the `context7` tools (see AGENTS.md Quick Reference).
- If you are unsure how to implement something or use a third-party library, use `gh_grep` to search public GitHub for up-to-date code examples.
- All new automation, documentation, and onboarding must propagate the `uv`-only setup and explicit agent research tooling guidance.

1. **Test the tooling**:
   ```bash
   just install
   just test
   just lint
   ```

2. **Try lifecycle hooks**:
   ```bash
   just test-file tests/test_lifecycle_hooks.py
   ```

3. **Make a commit**:
   ```bash
   git add .
   git commit -m "feat(tooling): add modern Python tooling"
   # Pre-commit hooks will run automatically
   ```

4. **Run the dev server**:
   ```bash
   just run
   ```

---

## References

- [just manual](https://just.systems/man/en/)
- [django-lifecycle docs](https://rsinger86.github.io/django-lifecycle/)
- [pre-commit docs](https://pre-commit.com/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [EditorConfig](https://editorconfig.org/)
