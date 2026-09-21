---
title: "Dependency Management"
---
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

## Documentation site dependencies

The documentation site is an Astro Starlight build, so its dependencies live in
`package.json` with `package-lock.json` as the lockfile. Install them with `npm ci` (run for
you by `just install`) and let Renovate propose upgrades; never hand-edit the lockfile.

The `docs` Python extra contains only `griffelib`, which
`scripts/generate_api_docs.py` uses to extract the API reference from docstrings.
