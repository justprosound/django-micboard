"""Security contracts for the repository release workflows."""

from __future__ import annotations

from pathlib import Path

WORKFLOW_ROOT = Path(__file__).parents[1] / ".github" / "workflows"


def _workflow(name: str) -> str:
    """Return one checked-in workflow as its public configuration contract."""
    return (WORKFLOW_ROOT / name).read_text(encoding="utf-8")


def test_release_workflows_have_single_responsibility_names() -> None:
    """Workflow filenames must distinguish preparation from publication."""
    assert not (WORKFLOW_ROOT / "release.yml").exists()
    assert (WORKFLOW_ROOT / "prepare-release.yml").is_file()


def test_workflow_topology_is_documented() -> None:
    """Maintainers must be able to discover every workflow and the release sequence."""
    guide = (WORKFLOW_ROOT / "README.md").read_text(encoding="utf-8")

    for workflow_name in (
        "ci.yml",
        "dependency-review.yml",
        "docs.yml",
        "prepare-release.yml",
        "publish-release.yml",
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
    assert "gh pr create" in release_workflow


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
    dependency_dispatch = release_workflow.index("gh workflow run dependency-review.yml")
    docs_dispatch = release_workflow.index("gh workflow run docs.yml")
    check_wait = release_workflow.index('gh run watch "$CI_RUN_ID"')
    dependency_wait = release_workflow.index('gh run watch "$DEPENDENCY_RUN_ID"')
    auto_merge = release_workflow.index("gh pr merge")
    publication_dispatch = release_workflow.index("gh workflow run publish-release.yml")

    assert ci_dispatch < check_wait < auto_merge
    assert dependency_dispatch < dependency_wait < auto_merge
    assert docs_dispatch < check_wait
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
    assert publication.count("needs: [validate-release, build-release, attest-release]") == 2
    assert "needs.attest-release.result == 'success'" in publication


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
