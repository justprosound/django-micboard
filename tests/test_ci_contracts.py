"""Static regression tests for self-contained, least-privilege CI."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ACTIONS = ROOT / ".github" / "actions"


def _workflow_job(workflow: str, job_name: str) -> str:
    """Return one top-level workflow job block for focused security assertions."""
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n.*?(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        workflow,
    )
    assert match is not None, f"Missing workflow job: {job_name}"
    return match.group(0)


def test_ci_coverage_gate_is_self_contained() -> None:
    """Coverage must fail locally and remain inspectable without an external service."""
    workflow = (WORKFLOWS / "ci.yml").read_text()
    release_workflow = (WORKFLOWS / "prepare-release.yml").read_text()
    justfile = (ROOT / "Justfile").read_text()
    thresholds = {
        int(value)
        for source in (workflow, justfile)
        for value in re.findall(r"--cov-fail-under=(\d+)", source)
    }

    assert thresholds == {95}
    assert "coverage.xml" in workflow
    assert "htmlcov/" in workflow
    assert "scripts/check_coverage_inventory.py" in workflow
    assert "gh workflow run ci.yml" in release_workflow
    assert "actions/upload-artifact@" in workflow
    assert "codecov" not in workflow.lower()
    assert "id-token: write" not in workflow


def test_every_trusted_publisher_uses_the_hardened_release_gate() -> None:
    """No alternate trusted-publishing workflow may bypass release verification."""
    publishers = {
        path.name: path.read_text()
        for path in WORKFLOWS.glob("*.yml")
        if "id-token: write" in path.read_text()
        or "pypa/gh-action-pypi-publish@" in path.read_text()
    }

    assert set(publishers) == {"publish-release.yml", "docs.yml"}
    release = publishers["publish-release.yml"]
    preparation = (WORKFLOWS / "prepare-release.yml").read_text()
    ci_workflow = (WORKFLOWS / "ci.yml").read_text()
    pre_commit_config = (ROOT / ".pre-commit-config.yaml").read_text()
    for required_gate in (
        "--cov-fail-under=95",
        "scripts/check_coverage_inventory.py",
        "python -m mypy micboard",
        "uv audit --locked --preview-features audit-command",
        "bandit -r micboard -ll",
        "pre-commit run --all-files",
    ):
        assert required_gate in ci_workflow
    assert "ruff-check" in pre_commit_config
    assert "ruff-format" in pre_commit_config
    for required_gate in (
        "scripts/validate_wheel.py",
        "scripts/smoke_test_installed_wheel.py",
    ):
        assert required_gate in release
    assert preparation.index("gh workflow run ci.yml") < preparation.index("gh pr merge")
    assert preparation.index("gh pr merge") < preparation.index(
        "gh workflow run publish-release.yml"
    )


def test_release_artifacts_are_built_once_and_digest_sealed() -> None:
    """The package must be built from the committed release source in a read-only job."""
    release = (WORKFLOWS / "publish-release.yml").read_text()
    build_job = _workflow_job(release, "build-release")

    assert "contents: read" in build_job
    assert "contents: write" not in build_job
    assert "id-token: write" not in build_job
    assert "ref: ${{ needs.validate-release.outputs.sha }}" in build_job
    assert "persist-credentials: false" in build_job
    assert "uv build --no-sources --sdist --clear" in build_job
    assert "uv build --no-sources --wheel dist/*.tar.gz" in build_job
    assert "uvx" not in build_job
    assert "--with-requirements release-tools.txt" in build_job
    assert "twine check dist/*" in build_job
    assert "sha256sum ./*.whl ./*.tar.gz ./*.spdx.json > SHA256SUMS" in build_job
    assert "sha256sum --check SHA256SUMS" in build_job
    assert "actions/upload-artifact@" in build_job


def test_release_publishers_only_verify_and_publish_sealed_artifacts() -> None:
    """OIDC jobs must not check out source or install mutable Python dependencies."""
    release = (WORKFLOWS / "publish-release.yml").read_text()

    assert "pypa/gh-action-pypi-publish@" not in release
    for job_name in ("publish-testpypi", "publish-pypi"):
        publish_job = _workflow_job(release, job_name)
        actions = re.findall(r"uses:\s+([^@\s]+)@", publish_job)

        assert "contents: read" in publish_job
        assert "contents: write" not in publish_job
        assert "id-token: write" in publish_job
        assert actions == [
            "astral-sh/setup-uv",
            "actions/download-artifact",
            "actions/download-artifact",
            "actions/upload-artifact",
        ]
        assert "actions/checkout@" not in publish_job
        assert "sha256sum --check SHA256SUMS" in publish_job
        assert "release-attestation-tools" in publish_job
        assert "--with-requirements release-tools.txt" in publish_job
        assert "python -m pypi_attestations sign" in publish_job
        assert "uv publish --trusted-publishing always --no-config" in publish_job
        assert publish_job.count("uv run") == 1
        for mutable_command in ("uv sync", "uvx", "uv build"):
            assert mutable_command not in publish_job


def test_release_writers_have_narrow_responsibilities() -> None:
    """Repository-write jobs must not build or publish distributions."""
    preparation = (WORKFLOWS / "prepare-release.yml").read_text()
    publication = (WORKFLOWS / "publish-release.yml").read_text()
    metadata_job = _workflow_job(preparation, "open-release-pr")
    merge_job = _workflow_job(preparation, "merge-release-pr")
    github_release_job = _workflow_job(publication, "create-github-release")
    metadata_actions = re.findall(r"uses:\s+([^@\s]+)@", metadata_job)

    assert "contents: write" in metadata_job
    assert "pull-requests: write" in metadata_job
    assert "id-token: write" not in metadata_job
    assert metadata_actions == ["actions/checkout"]
    assert metadata_job.index("actions/checkout@") < metadata_job.index(
        "uses: ./.github/actions/setup-uv-python"
    )
    assert "persist-credentials: false" in metadata_job
    assert "createCommitOnBranch" in metadata_job
    assert "git commit" not in metadata_job
    assert "git push" not in metadata_job
    assert "uv lock" in metadata_job
    assert "uv build" not in metadata_job
    assert "uv publish" not in metadata_job

    assert "actions: write" not in merge_job
    assert "contents: write" in merge_job
    assert "pull-requests: write" in merge_job
    assert "id-token: write" not in merge_job
    assert "uv build" not in merge_job
    assert "uv publish" not in merge_job

    assert "contents: write" in github_release_job
    assert "id-token: write" not in github_release_job
    assert "softprops/action-gh-release@" not in github_release_job
    assert "actions/download-artifact@" in github_release_job
    assert "gh release create" in github_release_job
    assert "gh release edit" in github_release_job
    assert "actions/checkout@" not in github_release_job
    assert "setup-uv@" not in github_release_job
    assert "uv " not in github_release_job
    assert "python" not in github_release_job.lower()


def test_release_changelog_uses_a_collision_resistant_output_delimiter() -> None:
    """A commit subject must not be able to terminate the multiline job output."""
    release = (WORKFLOWS / "prepare-release.yml").read_text()
    prepare_job = _workflow_job(release, "prepare-release")

    assert 'DELIMITER="release-changelog-$(git rev-parse HEAD)"' in prepare_job
    assert 'echo "content<<$DELIMITER"' in prepare_job
    assert 'echo "$DELIMITER"' in prepare_job
    assert "content<<EOF" not in prepare_job


def test_failed_publication_can_retry_exact_merged_metadata() -> None:
    """A retry must rebuild only the selected metadata commit already merged into main."""
    release = (WORKFLOWS / "publish-release.yml").read_text()
    validate_job = _workflow_job(release, "validate-release")

    assert "expected_sha:" in release
    assert "ref: ${{ inputs.expected_sha }}" in validate_job
    assert '"$(git rev-parse HEAD)" != "$EXPECTED_SHA"' in validate_job
    assert 'git merge-base --is-ancestor "$EXPECTED_SHA" origin/main' in validate_job
    assert 'grep -Fqx "version = \\"$RELEASE_VERSION\\"" pyproject.toml' in validate_job
    assert 'awk -v heading="## [$RELEASE_VERSION]"' in validate_job


def test_build_backend_dependencies_are_exactly_pinned() -> None:
    """PEP 517 build isolation must not resolve mutable dependency ranges."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert pyproject["build-system"]["requires"] == [
        "setuptools==83.0.0",
        "wheel==0.47.0",
    ]


def test_workflow_actions_are_pinned_to_commits() -> None:
    """Every remote GitHub Action must use an immutable 40-character commit SHA."""
    unpinned: list[str] = []
    action_sources = [
        *WORKFLOWS.glob("*.yml"),
        *ACTIONS.glob("**/*.yml"),
        *ACTIONS.glob("**/*.yaml"),
    ]
    for action_source in sorted(action_sources):
        for line_number, line in enumerate(action_source.read_text().splitlines(), start=1):
            match = re.search(r"\buses:\s+[^\s@]+@([^\s#]+)", line)
            if match and re.fullmatch(r"[0-9a-f]{40}", match.group(1)) is None:
                relative_path = action_source.relative_to(ROOT)
                unpinned.append(f"{relative_path}:{line_number}:{match.group(1)}")

    assert unpinned == []


def test_local_wheel_recipe_runs_the_ci_smoke_contract_in_development_mode() -> None:
    """Local package validation must catch the same installed-wheel failures as CI."""
    justfile = (ROOT / "Justfile").read_text()
    release_workflow = (WORKFLOWS / "publish-release.yml").read_text()
    smoke_script = (ROOT / "scripts" / "smoke_test_installed_wheel.py").read_text()

    assert "uv build --no-sources --sdist --clear" in justfile
    assert "uv build --no-sources --wheel" in justfile
    assert "scripts/smoke_test_installed_wheel.py" in justfile
    assert "scripts/smoke_test_installed_wheel.py" in release_workflow
    assert "scripts/validate_wheel.py" in release_workflow
    assert "DEBUG=True" in smoke_script


def test_dependency_automation_uses_canonical_uv_inputs() -> None:
    """Renovate must not edit generated exports or bypass their documentation check."""
    renovate_config = json.loads((ROOT / "renovate.json").read_text())
    docs_workflow = (WORKFLOWS / "docs.yml").read_text()
    pre_commit_config = (ROOT / ".pre-commit-config.yaml").read_text()

    assert "docs/requirements.txt" in renovate_config["ignorePaths"]
    assert "startsWith(github.head_ref, 'renovate/')" not in docs_workflow
    assert "scripts/check_docs_requirements.py" in pre_commit_config


def test_dependency_changes_receive_a_read_only_security_review() -> None:
    """Pull requests must reject newly introduced vulnerable dependencies."""
    workflow = (WORKFLOWS / "dependency-review.yml").read_text()

    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "actions/dependency-review-action@" in workflow
    assert "fail-on-severity: moderate" in workflow
    assert "fail-on-scopes: runtime, development, unknown" in workflow
    assert "base-ref: ${{ inputs.base_ref || github.event.pull_request.base.sha }}" in workflow
    assert "head-ref: ${{ inputs.head_ref || github.event.pull_request.head.sha }}" in workflow
    assert "persist-credentials: false" in workflow
    assert "pull-requests: write" not in workflow
    assert "secrets." not in workflow


def test_full_dependency_audit_runs_on_a_weekly_cadence() -> None:
    """New advisories must be detected even when no pull request updates the lockfile."""
    workflow = (WORKFLOWS / "ci.yml").read_text()

    assert "schedule:" in workflow
    assert 'cron: "17 6 * * 1"' in workflow
    assert "uv audit --locked --preview-features audit-command" in _workflow_job(
        workflow, "security"
    )


def test_ci_exposes_one_stable_required_check() -> None:
    """Branch protection must not depend on names generated by a changing test matrix."""
    workflow = (WORKFLOWS / "ci.yml").read_text()
    required_job = _workflow_job(workflow, "required")

    assert "name: CI required" in required_job
    assert "if: ${{ always() }}" in required_job
    assert "permissions: {}" in required_job
    assert "timeout-minutes: 5" in required_job
    assert "toJSON(needs)" in required_job
    assert 'all(.[]; .result == "success")' in required_job
    assert "actions/checkout@" not in required_job
    for dependency in ("lint", "package", "test", "security", "codeql"):
        assert f"      - {dependency}\n" in required_job


def test_security_sensitive_automation_has_declared_owners() -> None:
    """Workflow, toolchain, and agent-policy changes must request maintainer review."""
    codeowners = (ROOT / ".github" / "CODEOWNERS").read_text()

    for protected_path in (
        "/.github/workflows/",
        "/.github/actions/",
        "/.github/CODEOWNERS",
        "/.github/copilot-instructions.md",
        "/AGENTS.md",
        "/pyproject.toml",
        "/uv.lock",
    ):
        assert protected_path in codeowners
    assert "@justprosound/code-owners" in codeowners
    assert "@bandwith" not in codeowners
