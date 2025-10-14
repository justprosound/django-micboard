# Dependency Management

This project uses `pip-tools` to manage Python dependencies. The dependencies are defined in the `pyproject.toml` file, under the `[project.dependencies]` and `[project.optional-dependencies]` sections.

## Updating Dependencies

To update a dependency, you should:

1.  **Modify `pyproject.toml`**: Change the version specifier for the dependency you want to update. For example, to update `Django`, you could change `"Django>=4.2,<6.0"` to `"Django>=5.0,<6.0"`.

2.  **Re-compile the requirements files**: Run the following command to regenerate the `requirements.txt` and `dev-requirements.txt` files:

    ```bash
    pip-compile --extra=dev --output-file=dev-requirements.txt pyproject.toml
    pip-compile --output-file=requirements.txt pyproject.toml
    ```

3.  **Install the updated packages**: Update your local environment by running:

    ```bash
    pip install -r dev-requirements.txt
    ```

This process ensures that your dependency files are always up-to-date and your builds are reproducible.
