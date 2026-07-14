"""Static regression tests for self-contained, least-privilege CI."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_ci_coverage_gate_is_self_contained() -> None:
    """Coverage must fail locally and remain inspectable without an external service."""
    workflow = (WORKFLOWS / "ci.yml").read_text()
    release_workflow = (WORKFLOWS / "release.yml").read_text()
    justfile = (ROOT / "Justfile").read_text()
    thresholds = {
        int(value)
        for source in (workflow, release_workflow, justfile)
        for value in re.findall(r"--cov-fail-under=(\d+)", source)
    }

    assert thresholds == {49}
    assert "coverage.xml" in workflow
    assert "htmlcov/" in workflow
    assert "actions/upload-artifact@" in workflow
    assert "codecov" not in workflow.lower()
    assert "id-token: write" not in workflow


def test_workflow_actions_are_pinned_to_commits() -> None:
    """Every remote GitHub Action must use an immutable 40-character commit SHA."""
    unpinned: list[str] = []
    for workflow_path in sorted(WORKFLOWS.glob("*.yml")):
        for line_number, line in enumerate(workflow_path.read_text().splitlines(), start=1):
            match = re.search(r"\buses:\s+[^\s@]+@([^\s#]+)", line)
            if match and re.fullmatch(r"[0-9a-f]{40}", match.group(1)) is None:
                unpinned.append(f"{workflow_path.name}:{line_number}:{match.group(1)}")

    assert unpinned == []


def test_local_wheel_recipe_runs_the_ci_smoke_contract_in_development_mode() -> None:
    """Local package validation must catch the same installed-wheel failures as CI."""
    justfile = (ROOT / "Justfile").read_text()
    smoke_script = (ROOT / "scripts" / "smoke_test_installed_wheel.py").read_text()

    assert "scripts/smoke_test_installed_wheel.py" in justfile
    assert "DEBUG=True" in smoke_script


def test_dependency_automation_uses_canonical_uv_inputs() -> None:
    """Renovate must not edit generated exports or bypass their documentation check."""
    renovate_config = json.loads((ROOT / "renovate.json").read_text())
    docs_workflow = (WORKFLOWS / "docs.yml").read_text()
    pre_commit_config = (ROOT / ".pre-commit-config.yaml").read_text()

    assert "docs/requirements.txt" in renovate_config["ignorePaths"]
    assert "startsWith(github.head_ref, 'renovate/')" not in docs_workflow
    assert "scripts/check_docs_requirements.py" in pre_commit_config
