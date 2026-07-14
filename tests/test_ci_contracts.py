"""Static regression tests for self-contained, least-privilege CI."""

from __future__ import annotations

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
