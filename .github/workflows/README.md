# GitHub Actions workflows

GitHub discovers workflow definitions only in this directory. Each YAML file owns one lifecycle
responsibility; shared policy is enforced by the static contracts in `tests/test_ci_contracts.py`
and `tests/test_release_workflow_security.py`.

| Workflow | Responsibility | Trigger |
| --- | --- | --- |
| `ci.yml` | Lint, type check, package validation, 95% coverage, locked-dependency audit, Bandit, CodeQL, and one stable aggregate check | Push, pull request, weekly schedule, or manual dispatch |
| `dependency-review.yml` | Reject newly introduced vulnerable runtime and development dependencies | Pull request |
| `docs.yml` | Build and validate MkDocs output | Push, pull request, or manual dispatch |
| `prepare-release.yml` | Create the metadata pull request, observe exact required workflow runs, merge, and dispatch publication | Manual dispatch from `main` |
| `publish-release.yml` | Build and attest the exact merged commit, publish through an environment-bound OIDC token, and create the GitHub release | Dispatch from the preparation workflow on `main` |
| `warden.yml` | Review same-repository pull-request changes without exposing provider secrets to fork heads | Pull-request activity |

## Shared setup action

Repository-controlled Python jobs use `.github/actions/setup-uv-python/action.yml` as the single
toolchain bootstrap. The action pins the uv installer and uv release, verifies that uv is
available, and provisions the requested Python version. Dependency synchronization remains in
each job because the required extras and trust boundary differ by responsibility.

Externally triggered or credential-isolated jobs deliberately do not execute repository-local
actions. CodeQL retains its direct pinned setup while holding `security-events: write`; Warden
runs only its pinned review action; and the isolated attestation and publishing jobs hold
`id-token: write`, use immutable remote actions, and never check out the repository.

All read-only checkouts set `persist-credentials: false`. The sole exception is the metadata
writer that must push a generated release branch. Warden provider secrets exist only on its
review step, and that job runs only when the pull-request head belongs to this repository.

## Release sequence

The release lifecycle is **prepare -> validate -> merge -> attest -> publish**:

1. `prepare-release.yml` validates CalVer input and opens a release pull request.
2. A token limited to Actions dispatches `ci.yml`, `dependency-review.yml`, and `docs.yml` for the
   exact release head, finds those workflow runs by head SHA and dispatch time, and waits for all
   three to succeed.
3. A separate repository-write token requests the protected pull-request merge.
4. A third token limited to Actions passes the merge commit SHA to `publish-release.yml`.
5. Publication verifies that SHA belongs to `main`, builds it once, and seals the distributions
   with SHA-256 checksums.
6. An isolated OIDC job creates signed Sigstore build-provenance attestations for the sealed files.
7. The protected TestPyPI or PyPI environment publishes only after attestation succeeds.

Preparation never receives an OIDC token. Publishing jobs cannot modify repository contents, and
the GitHub release job cannot publish Python distributions. Explicit workflow-run observation
keeps the release gate effective even when repository branch rules are incomplete; maintainers
should still require pull-request review and the CI, documentation, and dependency-review checks
on `main`.

## Branch protection contract

Protect `main` with strict, GitHub-Actions-bound checks named `CI required`, `build-docs`, and
`dependency-review`. `CI required` aggregates lint, package, compatibility-matrix tests, Bandit,
locked-dependency audit, and CodeQL so matrix maintenance does not require branch-rule edits.
Require a code-owner approval, dismiss stale approvals, require approval after the latest push,
resolve review conversations, enforce linear history, and apply the rules to administrators.

## NIST SSDF evidence

[NIST SP 800-218 SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final) is the final compliance
baseline. [SSDF 1.2](https://csrc.nist.gov/pubs/sp/800/218/r1/ipd) remains an initial public draft,
so it informs future work but is not represented as a final requirement.

| SSDF practice | Repository evidence |
| --- | --- |
| `PO.3` Implement Supporting Toolchains | One pinned uv bootstrap, immutable action SHAs, Renovate-managed updates, and `uv.lock` |
| `PO.4` Define and Use Criteria for Software Security Checks | Static workflow contracts, pre-commit, mypy, Bandit, CodeQL, package checks, and a 95% coverage floor |
| `PO.5` Implement and Maintain Secure Environments | GitHub-hosted runners, explicit timeouts and concurrency, least-privilege job tokens, and protected publishing environments |
| `PS.1` Protect All Forms of Code from Unauthorized Access and Tampering | Pull-request release changes, CODEOWNERS, non-persisted read tokens, and exact-SHA release validation |
| `PS.2` Provide a Mechanism for Verifying Software Release Integrity | SHA-256 manifests plus signed Sigstore build-provenance attestations |
| `PS.3` Archive and Protect Each Software Release | Immutable workflow artifacts, exact-commit GitHub releases, and retained checksum manifests |
| `PW.4` Reuse Existing, Well-Secured Software When Feasible | Locked Python dependencies, full-lock auditing, and dependency review for new vulnerabilities and OpenSSF signals |
| `PW.7` Review and Analyze Human-Readable Code | Ruff, mypy, Bandit, CodeQL, pre-commit, Warden, and maintainer ownership rules |
| `PW.8` Test Executable Code | Django compatibility matrix, branch coverage, reusable-app validation, and installed-wheel smoke tests |
| `RV.1` Identify and Confirm Vulnerabilities | Weekly full-lock audit, dependency review, Dependabot security updates, Bandit, CodeQL, and secret scanning |
| `RV.2` Assess, Prioritize, and Remediate Vulnerabilities | Moderate-or-higher dependency failures, security gates, and automated dependency update tooling |
| `RV.3` Analyze Vulnerabilities to Identify Root Causes | Security regression contracts preserve release, authorization, and workflow trust-boundary fixes |
