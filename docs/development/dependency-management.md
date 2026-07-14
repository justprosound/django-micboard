# Dependency Management

This project uses uv to manage Python dependencies. Direct and optional dependencies are defined in `pyproject.toml`; reproducible versions are recorded in `uv.lock`.

## Updating Dependencies

To update a dependency, you should:

1. **Modify `pyproject.toml`**: change the direct dependency or optional-extra constraint.

2. **Refresh and validate the lockfile**:

    ```bash
    uv lock --upgrade-package <package-name>
    uv lock --check
    ```

3. **Sync and verify the complete supported surface**:

    ```bash
    uv sync --locked --all-extras
    just lint
    just test
    ```

`docs/requirements.txt` is exported from the locked `docs` extra. Regenerate it; never edit it
directly:

```bash
uv export --locked --no-dev --extra docs --no-emit-project \
  --output-file docs/requirements.txt
```

Renovate ignores this generated export and updates canonical dependency inputs instead. The
pre-commit suite rejects any export that drifts from `uv.lock`.
