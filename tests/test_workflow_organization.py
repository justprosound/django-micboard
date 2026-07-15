"""Maintainability contracts for the repository's GitHub Actions layout."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SETUP_ACTION = ROOT / ".github" / "actions" / "setup-uv-python" / "action.yml"


def _workflow_job(workflow_name: str, job_name: str) -> str:
    """Return one top-level job from a checked-in workflow contract."""
    workflow = (WORKFLOWS / workflow_name).read_text(encoding="utf-8")
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n.*?(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        workflow,
    )
    assert match is not None, f"Missing workflow job: {workflow_name}:{job_name}"
    return match.group(0)


def _workflow_job_names(workflow_name: str) -> list[str]:
    """Return stable top-level job identifiers without parsing step mappings."""
    workflow = (WORKFLOWS / workflow_name).read_text(encoding="utf-8")
    jobs = workflow.split("\njobs:\n", maxsplit=1)[1]
    return re.findall(r"(?m)^  ([a-zA-Z0-9_-]+):$", jobs)


def test_lint_job_uses_the_shared_uv_python_bootstrap() -> None:
    """The first Python quality gate must consume one documented setup interface."""
    lint_job = _workflow_job("ci.yml", "lint")

    assert SETUP_ACTION.is_file()
    assert "uses: ./.github/actions/setup-uv-python" in lint_job
    assert "astral-sh/setup-uv@" not in lint_job
    assert "uv python install" not in lint_job

    action = SETUP_ACTION.read_text(encoding="utf-8")
    assert "astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990" in action
    assert "uv python install" in action


def test_repository_controlled_python_jobs_share_the_bootstrap_action() -> None:
    """Repository-controlled Python jobs must not duplicate toolchain setup."""
    expected_jobs = {
        "ci.yml": ("lint", "package", "test", "security"),
        "docs.yml": ("build-docs",),
        "prepare-release.yml": ("open-release-pr",),
        "publish-release.yml": ("build-release",),
    }

    for workflow_name, job_names in expected_jobs.items():
        for job_name in job_names:
            job = _workflow_job(workflow_name, job_name)
            assert "uses: ./.github/actions/setup-uv-python" in job, (
                f"{workflow_name}:{job_name} bypasses the shared bootstrap"
            )
            assert "astral-sh/setup-uv@" not in job
            assert "uv python install" not in job


def test_workflow_guide_documents_shared_actions_and_privileged_exceptions() -> None:
    """Maintainers must see where setup is shared and where isolation takes precedence."""
    guide = (WORKFLOWS / "README.md").read_text(encoding="utf-8")
    normalized_guide = " ".join(guide.split())

    assert "`.github/actions/setup-uv-python/action.yml`" in guide
    assert "security-events: write" in guide
    assert "id-token: write" in guide
    assert "do not execute repository-local actions" in normalized_guide


def test_every_job_has_an_explicit_timeout() -> None:
    """A stalled external service must not consume an unbounded workflow run."""
    missing_timeouts = [
        f"{workflow_path.name}:{job_name}"
        for workflow_path in sorted(WORKFLOWS.glob("*.yml"))
        for job_name in _workflow_job_names(workflow_path.name)
        if "timeout-minutes:" not in _workflow_job(workflow_path.name, job_name)
    ]

    assert missing_timeouts == []


def test_externally_triggered_privileged_jobs_avoid_local_actions() -> None:
    """Elevated PR and OIDC jobs must execute only immutable remote actions."""
    privileged_jobs = (
        _workflow_job("ci.yml", "codeql"),
        _workflow_job("warden.yml", "review"),
        _workflow_job("publish-release.yml", "attest-release"),
        _workflow_job("publish-release.yml", "publish-testpypi"),
        _workflow_job("publish-release.yml", "publish-pypi"),
    )

    for job in privileged_jobs:
        assert "uses: ./.github/actions/" not in job


def test_every_checkout_declares_credential_persistence() -> None:
    """No job may leave its workflow token in local Git configuration."""
    workflows = [path.read_text(encoding="utf-8") for path in WORKFLOWS.glob("*.yml")]
    checkout_count = sum(workflow.count("uses: actions/checkout@") for workflow in workflows)
    persistence_count = sum(workflow.count("persist-credentials:") for workflow in workflows)
    explicit_writers = sum(workflow.count("persist-credentials: true") for workflow in workflows)

    assert checkout_count == persistence_count
    assert explicit_writers == 0


def test_warden_limits_secrets_to_trusted_review_execution() -> None:
    """Fork code must not receive Warden credentials or a write-capable review token."""
    review_job = _workflow_job("warden.yml", "review")
    action_step = review_job[review_job.index("uses: getsentry/warden@") :]
    job_before_steps = review_job[: review_job.index("steps:")]

    assert "if: github.event.pull_request.head.repo.full_name == github.repository" in review_job
    assert "${{ secrets." not in job_before_steps
    assert "WARDEN_OPENAI_API_KEY: ${{ secrets.WARDEN_OPENAI_API_KEY }}" in action_step
    assert "WARDEN_ANTHROPIC_API_KEY: ${{ secrets.WARDEN_ANTHROPIC_API_KEY }}" in action_step
