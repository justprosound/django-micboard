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
| `publish-release.yml` | Build the exact merge once, generate and attest its SBOM, promote through TestPyPI, publish with PEP 740 attestations, and create the GitHub release | Dispatch from the preparation workflow on `main` |
| `recover-github-release.yml` | Reverify the original PyPI artifact from a failed publication run and finish only its GitHub release | Manual break-glass dispatch from `main` |
| `warden.yml` | Optional AI review for same-repository pull requests after a provider secret is configured | Pull-request activity when enabled |

## Shared setup action

Repository-controlled Python jobs use `.github/actions/setup-uv-python/action.yml` as the single
toolchain bootstrap. The action pins the uv installer and uv release, verifies that uv is
available, and provisions the requested Python version. Dependency synchronization remains in
each job because the required extras and trust boundary differ by responsibility.

Externally triggered or credential-isolated jobs deliberately do not execute repository-local
actions. CodeQL retains its direct pinned setup while holding `security-events: write`; when
enabled, Warden runs only its pinned review action; and the isolated attestation and publishing
jobs hold `id-token: write`, use immutable remote actions, and never check out the repository.

All checkouts set `persist-credentials: false`. The metadata writer creates one atomic commit with
GitHub's API and no custom author, committer, or signature fields; GitHub signs that bot commit and
the workflow verifies it before opening the pull request. Optional Warden provider secrets are
scoped to its review step, and that job runs only when the pull-request head belongs to this
repository.

## Release sequence

The release lifecycle is **prepare -> validate -> merge -> attest -> publish**:

1. `prepare-release.yml` derives the next UTC CalVer when its optional override is blank. The first
   daily release uses `YY.MM.DD`; additional same-day releases increment `.1`, `.2`, and so on. It
   validates the resolved version, asks GitHub to create a verified bot-signed metadata commit, and
   opens a release pull request.
2. A token limited to Actions dispatches `ci.yml`, `dependency-review.yml`, and `docs.yml` for the
   exact release head, finds those workflow runs by head SHA and dispatch time, and waits for all
   three to succeed.
3. A separate repository-write token requests the protected pull-request merge.
4. A third token limited to Actions passes the merge commit SHA to `publish-release.yml`.
5. Publication verifies that SHA belongs to `main`, uses its commit timestamp as
   `SOURCE_DATE_EPOCH` for reproducible archives, builds with registry-standard dependency
   metadata, generates an SPDX JSON SBOM, and seals the wheel, source archive, and SBOM with
   SHA-256 checksums.
6. An isolated OIDC job creates separate Sigstore build-provenance and SBOM attestations for the
   sealed wheel and source archive.
7. The protected `testpypi` job uses a hash-locked, uv-exported toolchain to sign environment-bound
   PEP 740 publish attestations, then uploads the wheel and source archive with those attestations.
8. A read-only job compares TestPyPI's published digests with `SHA256SUMS`; production cannot reach
   approval until this promotion check succeeds.
9. After the release pull request merges, the maintainer uses the exact commands in the preparation
   run summary to create and push a signed annotated tag for that merge commit.
10. The same workflow run pauses at the protected `pypi-release` environment until the Code Owners
    team explicitly approves the deployment. The job requires GitHub to verify the tag signature
    and exact commit target, signs fresh PyPI-environment PEP 740 attestations for the same sealed
    files, and publishes through OIDC Trusted Publishing. Keeping both registries in one run
    prevents a later rebuild from reusing an already-published version.
11. The GitHub release job rechecks the signed tag, downloads the registry-signed files, verifies
    their checksums, creates a draft release with the wheel, source archive, SPDX SBOM, PEP 740
    attestations, and checksum manifest, then publishes only after every asset is attached.

Preparation never receives an OIDC token. Publishing jobs cannot modify repository contents, and
the GitHub release job cannot publish Python distributions. Explicit workflow-run observation
keeps the release gate effective even when repository branch rules are incomplete. The production
environment approval is intentionally separate from pull-request validation so a single human
maintainer can operate the repository without weakening the automated release gates.

## GitHub release recovery

Use `recover-github-release.yml` only when `publish-pypi` succeeded but the final
`create-github-release` job failed. Supply the failed publication run ID, its exact released source
commit, and its CalVer version. Recovery rejects any other workflow shape, downloads the retained
`pypi-distribution` artifact instead of rebuilding it, and verifies its checksum manifest, package
version, source contents, and GitHub Sigstore attestations in a read-only job. A one-day intermediate
artifact then crosses into a separate `contents: write` job, which pauses for `pypi-release`
environment approval, requires the same GitHub-verified signed tag to target the released commit,
then creates a draft, attaches every original asset, and publishes it.

Do not start a new publication run to recover an existing registry version. Registry indexes must
never be used as permission to replace or reconstruct the original release attestations.

## First-release registry and immutability setup

Before the first publication, create pending Trusted Publishers on both PyPI and TestPyPI with
project name `django-micboard`, owner `justprosound`, repository `django-micboard`, workflow
`publish-release.yml`, and the matching environment name: `pypi-release` or `testpypi`. Do not add
registry API tokens or passwords; both registries exchange the environment-bound GitHub OIDC
identity for a short-lived upload token.

In repository **Settings**, scroll to **Releases** and select **Enable release immutability** before
creating the first release. GitHub applies this only to future releases. The workflow deliberately
creates a draft, attaches every integrity asset, and publishes it last so the completed release is
ready for immutable enforcement.

Consumers can verify build provenance with:

```bash
gh attestation verify django_micboard-<version>-py3-none-any.whl \
  --repo justprosound/django-micboard
gh attestation verify django_micboard-<version>-py3-none-any.whl \
  --repo justprosound/django-micboard \
  --predicate-type https://spdx.dev/Document/v2.3
```

## Branch protection contract

Keep repository default workflow permissions read-only and enable
**Allow GitHub Actions to create and approve pull requests**. The release workflow needs that
explicit repository capability to open its metadata pull request. Each job still receives only its
declared token permissions. Keep public-fork approval at **first-time contributors**. The first
generated release pull request may pause its `pull_request` runs until a maintainer approves
`github-actions[bot]` once; approve only the runs bound to the generated release commit rather than
weakening the approval policy.

Protect `main` with strict, GitHub-Actions-bound checks named `CI required`, `build-docs`, and
`dependency-review`. `CI required` aggregates lint, package, compatibility-matrix tests, Bandit,
locked-dependency audit, and CodeQL so matrix maintenance does not require branch-rule edits.
Keep pull requests mandatory with zero required pull-request approvals: GitHub does not permit a
pull-request author to approve their own change, so requiring a review would deadlock the sole
human maintainer. CODEOWNERS remains non-blocking and routes security-sensitive changes to
`@justprosound/code-owners` for visibility. Require signed commits, resolve review conversations,
enforce linear history, disallow force pushes and branch deletion, and apply the rules to
administrators. Allow only squash merges, enable auto-merge, and delete merged branches.

Protect the production `pypi-release` environment with the `@justprosound/code-owners` team as a
required reviewer, allow self-review so the sole team member can release, and limit deployments to
protected branches. Disallow administrator bypass so every production publication records an
explicit approval. Keep the `testpypi` environment limited to protected branches without a reviewer
so TestPyPI validation remains automated. This moves the one deliberate human decision to the
point of production publication while every source change still passes the exact automated branch
gates.

## NIST SSDF evidence

[NIST SP 800-218 SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final) is the final compliance
baseline. [SSDF 1.2](https://csrc.nist.gov/pubs/sp/800/218/r1/ipd) remains an initial public draft,
so it informs future work but is not represented as a final requirement.

| SSDF practice | Repository evidence |
| --- | --- |
| `PO.3` Implement Supporting Toolchains | One pinned uv bootstrap, immutable action SHAs, Renovate-managed updates, and `uv.lock` |
| `PO.4` Define and Use Criteria for Software Security Checks | Static workflow contracts, pre-commit, mypy, Bandit, CodeQL, package checks, and a 95% coverage floor |
| `PO.5` Implement and Maintain Secure Environments | GitHub-hosted runners, explicit timeouts and concurrency, least-privilege job tokens, protected publishing environments, and explicit production deployment approval |
| `PS.1` Protect All Forms of Code from Unauthorized Access and Tampering | Mandatory pull requests, strict app-bound checks, signed linear history, CODEOWNERS routing, non-persisted read tokens, and a GitHub-verified maintainer-signed release tag bound to the exact release SHA |
| `PS.2` Provide a Mechanism for Verifying Software Release Integrity | SHA-256 manifests, signed Sigstore build-provenance and SPDX SBOM attestations, and environment-bound PEP 740 publish attestations |
| `PS.3` Archive and Protect Each Software Release | Draft-first immutable GitHub releases containing the exact wheel, source archive, SPDX SBOM, PEP 740 attestations, and checksum manifest |
| `PW.4` Reuse Existing, Well-Secured Software When Feasible | Locked Python dependencies, full-lock auditing, and dependency review for new vulnerabilities and OpenSSF signals |
| `PW.7` Review and Analyze Human-Readable Code | Ruff, mypy, Bandit, CodeQL, pre-commit, and maintainer ownership rules |
| `PW.8` Test Executable Code | Django compatibility matrix, branch coverage, reusable-app validation, and installed-wheel smoke tests |
| `RV.1` Identify and Confirm Vulnerabilities | Weekly full-lock audit, dependency review, Dependabot security updates, Bandit, CodeQL, and secret scanning |
| `RV.2` Assess, Prioritize, and Remediate Vulnerabilities | Moderate-or-higher dependency failures, security gates, and automated dependency update tooling |
| `RV.3` Analyze Vulnerabilities to Identify Root Causes | Security regression contracts preserve release, authorization, and workflow trust-boundary fixes |
