# GitHub Actions workflows

GitHub discovers workflow definitions only in this directory. Each YAML file owns one lifecycle
responsibility; shared policy is enforced by the static contracts in `tests/test_ci_contracts.py`
and `tests/test_release_workflow_security.py`.

| Workflow | Responsibility | Trigger |
| --- | --- | --- |
| `ci.yml` | Lint, type check, package validation, 95% coverage, Bandit, and CodeQL | Push, pull request, or manual dispatch |
| `docs.yml` | Build and validate MkDocs output | Push, pull request, or manual dispatch |
| `prepare-release.yml` | Create the metadata pull request, dispatch required checks, and request protected auto-merge | Manual dispatch from `main` |
| `publish-release.yml` | Build the exact merged commit, publish through an environment-bound OIDC token, and create the GitHub release | Dispatch from the preparation workflow on `main` |
| `warden.yml` | Review pull-request changes | Pull-request activity |

## Shared setup action

Repository-controlled Python jobs use `.github/actions/setup-uv-python/action.yml` as the single
toolchain bootstrap. The action pins the uv installer and uv release, verifies that uv is
available, and provisions the requested Python version. Dependency synchronization remains in
each job because the required extras and trust boundary differ by responsibility.

Externally triggered or credential-isolated jobs deliberately do not execute repository-local
actions. CodeQL retains its direct pinned setup while holding `security-events: write`; Warden
runs only its pinned review action; and the isolated publishing jobs retain direct pinned setup
while holding `id-token: write` and never check out the repository.

## Release sequence

The release lifecycle is **prepare -> validate -> merge -> publish**:

1. `prepare-release.yml` validates CalVer input and opens a release pull request.
2. It explicitly dispatches `ci.yml` and `docs.yml` for the release branch.
3. Protected-branch auto-merge waits for every required check.
4. The merge commit SHA is passed to `publish-release.yml`.
5. Publication verifies that SHA belongs to `main`, builds it once, seals the artifacts with
   SHA-256 checksums, and publishes from the protected TestPyPI or PyPI environment.

Preparation never receives an OIDC token. Publishing jobs cannot modify repository contents, and
the GitHub release job cannot publish Python distributions.
