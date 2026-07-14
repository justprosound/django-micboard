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
        "docs.yml",
        "prepare-release.yml",
        "publish-release.yml",
        "warden.yml",
    ):
        assert f"`{workflow_name}`" in guide
    assert "prepare -> validate -> merge -> publish" in guide


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
    """Publishing must follow required checks and the protected pull-request merge."""
    release_workflow = _workflow("prepare-release.yml")

    ci_dispatch = release_workflow.index("gh workflow run ci.yml")
    docs_dispatch = release_workflow.index("gh workflow run docs.yml")
    auto_merge = release_workflow.index("gh pr merge")
    publication_dispatch = release_workflow.index("gh workflow run publish-release.yml")

    assert ci_dispatch < auto_merge
    assert docs_dispatch < auto_merge
    assert auto_merge < publication_dispatch


def test_publication_builds_the_exact_release_merge() -> None:
    """A later main commit must not change the distributions selected for publication."""
    preparation_workflow = _workflow("prepare-release.yml")
    publication_workflow = _workflow("publish-release.yml")

    assert '--field expected_sha="$MERGE_SHA"' in preparation_workflow
    assert "expected_sha:" in publication_workflow
    assert "ref: ${{ inputs.expected_sha }}" in publication_workflow
    assert 'git merge-base --is-ancestor "$EXPECTED_SHA" origin/main' in publication_workflow
