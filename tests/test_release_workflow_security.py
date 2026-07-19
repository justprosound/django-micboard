"""Security contracts for the repository release workflows."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW_ROOT = Path(__file__).parents[1] / ".github" / "workflows"


def _workflow(name: str) -> str:
    """Return one checked-in workflow as its public configuration contract."""
    return (WORKFLOW_ROOT / name).read_text(encoding="utf-8")


def test_release_workflows_have_single_responsibility_names() -> None:
    """Workflow filenames must distinguish preparation from publication."""
    assert not (WORKFLOW_ROOT / "release.yml").exists()
    assert (WORKFLOW_ROOT / "prepare-release.yml").is_file()
    assert (WORKFLOW_ROOT / "recover-github-release.yml").is_file()


def test_release_version_defaults_to_the_next_utc_calver() -> None:
    """Blank versions increment safely while retaining a validated backfill override."""
    preparation = _workflow("prepare-release.yml")

    assert (
        'description: "CalVer override (YY.MM.DD[.N]); blank uses the next UTC daily release"'
        in preparation
    )
    assert "required: false" in preparation
    assert "REQUESTED_VERSION: ${{ inputs.version }}" in preparation
    assert "uses: ./.github/actions/setup-uv-python" in preparation
    assert (
        'uv tool run bump-my-version bump patch --new-version "$REQUESTED_VERSION"' in preparation
    )
    assert "uv tool run bump-my-version bump patch" in preparation
    assert (
        "RELEASE_VERSION=\"$(grep '^version = ' pyproject.toml | cut -d '\\\"' -f 2)\""
        in preparation
    )
    assert 'echo "### Preparing release v$RELEASE_VERSION" >> "$GITHUB_STEP_SUMMARY"' in preparation
    assert (
        "run-name: \"Prepare release · ${{ inputs.version || 'automatic CalVer' }}\"" in preparation
    )


def test_release_workflows_accept_positive_same_day_calver_revisions() -> None:
    """Preparation and publication must agree on the collision-safe version grammar."""
    version_pattern = "^[0-9]{2}\\.[0-9]{2}\\.[0-9]{2}(\\.[1-9][0-9]*)?$"

    assert version_pattern in _workflow("prepare-release.yml")
    assert version_pattern in _workflow("publish-release.yml")


def test_release_builds_are_reproducible_across_safe_retries() -> None:
    """A source commit must produce registry-identical wheel and source archives."""
    publication = _workflow("publish-release.yml")

    assert "source-date-epoch: ${{ steps.release.outputs.source-date-epoch }}" in publication
    assert "git show -s --format=%ct HEAD" in publication
    assert (
        "SOURCE_DATE_EPOCH: ${{ needs.validate-release.outputs.source-date-epoch }}" in publication
    )
    sdist_build = publication.index("uv build --no-sources --sdist --clear")
    normalization = publication.index("scripts/normalize_sdist.py")
    wheel_build = publication.index("uv build --no-sources --wheel dist/*.tar.gz")
    assert sdist_build < normalization < wheel_build


def test_github_release_recovery_reuses_only_verified_pypi_artifacts() -> None:
    """Recovery must preserve published bytes and keep write authority in a separate job."""
    recovery = _workflow("recover-github-release.yml")
    verify_job = recovery[recovery.index("  verify-recovery:") :]
    verify_job = verify_job[: verify_job.index("  create-github-release:")]
    release_job = recovery[recovery.index("  create-github-release:") :]

    assert "SOURCE_RUN_ID: ${{ inputs.source_run_id }}" in verify_job
    assert '.path == ".github/workflows/publish-release.yml"' in verify_job
    assert 'select(.name == "publish-pypi" and .conclusion == "success")' in verify_job
    assert "run-id: ${{ inputs.source_run_id }}" in verify_job
    assert "github-token: ${{ github.token }}" in verify_job
    assert "sha256sum --check SHA256SUMS" in verify_job
    assert "https://pypi.org/pypi/django-micboard/$RELEASE_VERSION/json" in verify_job
    assert "gh attestation verify" in verify_job
    assert "scripts/validate_wheel.py" in verify_job
    assert "actions: read" in verify_job
    assert "contents: write" not in verify_job
    assert "needs: verify-recovery" in release_job
    assert "contents: write" in release_job
    assert "actions: read" not in release_job
    assert '--repo "$GITHUB_REPOSITORY"' in release_job


def test_release_writers_require_the_verified_signed_tag_for_the_exact_commit() -> None:
    """Registry and GitHub publication must consume a maintainer-signed immutable identity."""
    publication = _workflow("publish-release.yml")
    pypi_job = publication[publication.index("  publish-pypi:") :]
    pypi_job = pypi_job[: pypi_job.index("  create-github-release:")]
    release_jobs = (
        pypi_job,
        publication[publication.index("  create-github-release:") :],
        _workflow("recover-github-release.yml").split("  create-github-release:", 1)[1],
    )

    for job in release_jobs:
        assert "git/ref/tags/$RELEASE_TAG" in job
        assert "git/tags/$TAG_OBJECT_SHA" in job
        assert '.object.type == "commit"' in job
        assert ".object.sha == $expected_sha" in job
        assert ".verification.verified == true" in job

    for github_release_job in release_jobs[1:]:
        assert "--verify-tag" in github_release_job
        assert "--target" not in github_release_job
        assert "targetCommitish" not in github_release_job


def test_publication_retry_allows_its_existing_verified_release_tag() -> None:
    """A pre-PyPI retry must reach the exact-target signature gate instead of failing early."""
    preparation = _workflow("prepare-release.yml")
    publication = _workflow("publish-release.yml")
    validation_job = publication[publication.index("  validate-release:") :]
    validation_job = validation_job[: validation_job.index("  build-release:")]

    assert 'git show-ref --verify --quiet "refs/tags/v$RELEASE_VERSION"' in preparation
    assert 'git show-ref --verify --quiet "refs/tags/v$RELEASE_VERSION"' not in validation_job


def test_release_preparation_surfaces_the_human_signing_ceremony() -> None:
    """Solo maintainers must receive exact tag commands before production approval."""
    preparation = _workflow("prepare-release.yml")
    dispatch_job = preparation[preparation.index("  dispatch-publication:") :]

    assert "Sign release tag before production approval" in dispatch_job
    assert "git tag -s v$RELEASE_VERSION $MERGE_SHA -m 'Release $RELEASE_VERSION'" in dispatch_job
    assert "git push origin refs/tags/v$RELEASE_VERSION" in dispatch_job
    assert "pypi-release" in dispatch_job


def test_workflow_topology_is_documented() -> None:
    """Maintainers must be able to discover every workflow and the release sequence."""
    guide = (WORKFLOW_ROOT / "README.md").read_text(encoding="utf-8")

    for workflow_name in (
        "auto-release.yml",
        "ci.yml",
        "dependency-review.yml",
        "docs.yml",
        "prepare-release.yml",
        "publish-release.yml",
        "recover-github-release.yml",
        "scorecard.yml",
        "warden.yml",
    ):
        assert f"`{workflow_name}`" in guide
    assert "prepare -> validate -> merge -> attest -> publish" in guide


def test_solo_maintainer_release_gate_is_documented() -> None:
    """The checked-in protection contract must not reintroduce a self-review deadlock."""
    guide = (WORKFLOW_ROOT / "README.md").read_text(encoding="utf-8")

    assert "zero required pull-request approvals" in guide
    assert "CODEOWNERS remains non-blocking" in guide
    assert "allow self-review so the sole team member can release" in guide
    assert "Disallow administrator bypass" in guide
    assert "strict, GitHub-Actions-bound checks" in guide
    assert "production `pypi-release` environment" in guide
    assert "`testpypi` environment" in guide
    assert "Allow GitHub Actions to create and approve pull requests" in guide
    assert "first-time contributors" in guide
    assert "`github-actions[bot]`" in guide


def test_workflow_runs_have_contextual_ui_names() -> None:
    """The Actions run list must identify the branch, pull request, or release at a glance."""
    unnamed_workflows = [
        path.name
        for path in sorted(WORKFLOW_ROOT.glob("*.yml"))
        if "\nrun-name:" not in path.read_text(encoding="utf-8")
    ]

    assert unnamed_workflows == []


def test_release_metadata_reaches_main_through_a_pull_request() -> None:
    """Release preparation must never push its metadata commit directly to main."""
    release_workflow = _workflow("prepare-release.yml")

    assert "git push origin HEAD:main" not in release_workflow
    assert "peter-evans/create-pull-request" in release_workflow


def test_release_metadata_commit_is_verified_without_a_stored_signing_key() -> None:
    """GitHub must author the generated commit so signed-commit protection remains enforceable."""
    release_workflow = _workflow("prepare-release.yml")
    metadata_job = release_workflow[release_workflow.index("  open-release-pr:") :]
    metadata_job = metadata_job[: metadata_job.index("  validate-release-pr:")]

    assert "git commit" not in metadata_job
    assert "git push" not in metadata_job
    assert "git config --local user" not in metadata_job


def test_distribution_publication_runs_only_from_main() -> None:
    """Preparing a release PR must not expose package-publishing credentials."""
    preparation_workflow = _workflow("prepare-release.yml")
    publication_workflow = _workflow("publish-release.yml")

    assert "uv publish" not in preparation_workflow
    assert "github.ref == 'refs/heads/main'" in publication_workflow
    assert "uv publish" in publication_workflow


def test_release_pr_passes_required_checks_before_merge_and_publication() -> None:
    """Publishing must follow observed successful checks and the pull-request merge."""
    release_workflow = _workflow("prepare-release.yml")

    ci_dispatch = release_workflow.index("gh workflow run ci.yml")
    check_wait = release_workflow.index('gh run watch "$CI_RUN_ID"')
    auto_merge = release_workflow.index("gh pr merge")
    publication_dispatch = release_workflow.index("gh workflow run publish-release.yml")

    assert ci_dispatch < check_wait < auto_merge
    assert auto_merge < publication_dispatch


def test_release_authority_is_separated_by_job() -> None:
    """Workflow dispatch, repository writes, and publication dispatch must not share a token."""
    release_workflow = _workflow("prepare-release.yml")
    validate_job = release_workflow[release_workflow.index("  validate-release-pr:") :]
    validate_job = validate_job[: validate_job.index("  merge-release-pr:")]
    merge_job = release_workflow[release_workflow.index("  merge-release-pr:") :]
    merge_job = merge_job[: merge_job.index("  dispatch-publication:")]
    publish_job = release_workflow[release_workflow.index("  dispatch-publication:") :]

    assert "actions: write" in validate_job
    assert "contents: write" not in validate_job
    assert "pull-requests: write" not in validate_job
    assert "needs: [prepare-release, open-release-pr, validate-release-pr]" in merge_job
    assert "contents: write" in merge_job
    assert "pull-requests: write" in merge_job
    assert "actions: write" not in merge_job
    assert "needs: [prepare-release, merge-release-pr]" in publish_job
    assert "actions: write" in publish_job
    assert "contents: write" not in publish_job
    assert "pull-requests: write" not in publish_job


def test_release_artifacts_receive_build_provenance_before_publication() -> None:
    """Each sealed distribution must have signed provenance before either registry receives it."""
    publication = _workflow("publish-release.yml")
    attestation_job = publication[publication.index("  attest-release:") :]
    attestation_job = attestation_job[: attestation_job.index("  publish-testpypi:")]

    assert "attestations: write" in attestation_job
    assert "id-token: write" in attestation_job
    assert "actions/attest@" in attestation_job
    assert "actions/download-artifact@" in attestation_job
    assert "sha256sum --check SHA256SUMS" in attestation_job
    assert "actions/checkout@" not in attestation_job
    assert "uses: ./.github/actions/" not in attestation_job
    assert "needs: [validate-release, build-release, attest-release]" in publication
    assert (
        "needs: [validate-release, build-release, attest-release, verify-testpypi]" in publication
    )
    assert "needs.attest-release.result == 'success'" in publication


def test_release_artifacts_include_a_signed_spdx_sbom() -> None:
    """Consumers must receive an SBOM bound to the exact wheel and source distribution."""
    publication = _workflow("publish-release.yml")
    build_job = publication[publication.index("  build-release:") :]
    build_job = build_job[: build_job.index("  attest-release:")]
    attestation_job = publication[publication.index("  attest-release:") :]
    attestation_job = attestation_job[: attestation_job.index("  publish-testpypi:")]

    assert "anchore/sbom-action@" in build_job
    assert "format: spdx-json" in build_job
    assert "output-file: dist/django-micboard-" in build_job
    assert "upload-artifact: false" in build_job
    assert "./*.spdx.json" in build_job
    assert "sbom-path: dist/django-micboard-" in attestation_job
    assert attestation_job.count("actions/attest@") == 2


def test_sbom_generator_uses_a_valid_syft_release_tag() -> None:
    """The SBOM action must receive Syft's v-prefixed GitHub release tag."""
    publication = _workflow("publish-release.yml")
    build_job = publication[publication.index("  build-release:") :]
    build_job = build_job[: build_job.index("  attest-release:")]

    assert re.search(r'syft-version: "v\d+\.\d+\.\d+"', build_job)


def test_release_artifact_uploads_are_retry_safe() -> None:
    """A failed job attempt must be able to replace its own immutable named artifact."""
    publication = _workflow("publish-release.yml")

    assert publication.count("actions/upload-artifact@") == 4
    assert publication.count("overwrite: true") == 4


def test_registry_publishers_create_environment_bound_pep740_attestations() -> None:
    """Each registry upload must carry publish attestations signed by its own OIDC identity."""
    publication = _workflow("publish-release.yml")
    build_job = publication[publication.index("  build-release:") :]
    build_job = build_job[: build_job.index("  attest-release:")]

    assert "uv export --locked --only-group release" in build_job
    assert "release-attestation-tools" in build_job
    for start, end in (
        ("  publish-testpypi:", "  publish-pypi:"),
        ("  publish-pypi:", "  create-github-release:"),
    ):
        publish_job = publication[publication.index(start) : publication.index(end)]
        signing = publish_job.index("python -m pypi_attestations sign")
        upload = publish_job.index("uv publish --trusted-publishing always --no-config")

        assert "release-attestation-tools" in publish_job
        assert "--with-requirements release-tools.txt" in publish_job
        assert "*.publish.attestation" in publish_job
        assert signing < upload


def test_production_promotes_the_testpypi_verified_build() -> None:
    """Production approval must follow an integrity check of the same files on TestPyPI."""
    publication = _workflow("publish-release.yml")
    testpypi_job = publication[publication.index("  publish-testpypi:") :]
    testpypi_job = testpypi_job[: testpypi_job.index("  verify-testpypi:")]
    verification_job = publication[publication.index("  verify-testpypi:") :]
    verification_job = verification_job[: verification_job.index("  publish-pypi:")]
    pypi_job = publication[publication.index("  publish-pypi:") :]
    pypi_job = pypi_job[: pypi_job.index("  create-github-release:")]

    assert "needs: [validate-release, build-release, attest-release]" in testpypi_job
    assert "needs: [validate-release, build-release, publish-testpypi]" in verification_job
    assert "test.pypi.org/pypi/django-micboard/" in verification_job
    assert "SHA256SUMS" in verification_job
    assert "needs: [validate-release, build-release, attest-release, verify-testpypi]" in pypi_job


def test_github_release_publishes_the_verified_supply_chain_assets_atomically() -> None:
    """GitHub releases must expose sealed artifacts and stay draft until every asset is attached."""
    publication = _workflow("publish-release.yml")
    github_release_job = publication[publication.index("  create-github-release:") :]

    assert "softprops/action-gh-release@" not in github_release_job
    assert "actions/download-artifact@" in github_release_job
    assert "gh release create" in github_release_job
    assert "gh release view" in github_release_job
    assert "gh release upload" in github_release_job
    assert "--draft" in github_release_job
    assert "--clobber" in github_release_job
    assert "isDraft" in github_release_job
    assert "dist/*.whl" in github_release_job
    assert "dist/*.tar.gz" in github_release_job
    assert "dist/*.spdx.json" in github_release_job
    assert "dist/*.publish.attestation" in github_release_job
    assert "dist/SHA256SUMS" in github_release_job
    assert github_release_job.count('--repo "$GITHUB_REPOSITORY"') == 4
    assert 'gh release edit "$RELEASE_TAG" --draft=false' in github_release_job
    assert github_release_job.index("gh release create") < github_release_job.index(
        "gh release upload"
    )
    assert github_release_job.index("gh release upload") < github_release_job.index(
        'gh release edit "$RELEASE_TAG" --draft=false'
    )


def test_testpypi_verification_and_production_are_one_atomic_release() -> None:
    """A release must not rebuild a TestPyPI version in a later production workflow run."""
    preparation = _workflow("prepare-release.yml")
    publication = _workflow("publish-release.yml")
    pypi_job = publication[publication.index("  publish-pypi:") :]
    pypi_job = pypi_job[: pypi_job.index("  create-github-release:")]
    github_release_job = publication[publication.index("  create-github-release:") :]

    assert "test_only:" not in preparation
    assert "test_only:" not in publication
    assert "needs: [validate-release, build-release, attest-release, verify-testpypi]" in pypi_job
    assert "if:" not in pypi_job
    assert "always()" in github_release_job
    assert "inputs.test_only" not in github_release_job


def test_ssdf_workflow_evidence_is_documented() -> None:
    """Maintainers must be able to trace workflow controls to the final SSDF baseline."""
    guide = _workflow("README.md")

    assert "NIST SP 800-218 SSDF 1.1" in guide
    assert "SSDF 1.2" in guide
    for practice in ("PO.3", "PO.4", "PO.5", "PS.1", "PS.2", "PW.7", "PW.8", "RV.1"):
        assert f"`{practice}`" in guide


def test_publication_builds_the_exact_release_merge() -> None:
    """A later main commit must not change the distributions selected for publication."""
    preparation_workflow = _workflow("prepare-release.yml")
    publication_workflow = _workflow("publish-release.yml")

    assert '--field expected_sha="$MERGE_SHA"' in preparation_workflow
    assert "expected_sha:" in publication_workflow
    assert "ref: ${{ inputs.expected_sha }}" in publication_workflow
    assert 'git merge-base --is-ancestor "$EXPECTED_SHA" origin/main' in publication_workflow
