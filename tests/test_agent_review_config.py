"""Code review stays on the host unless the maintainers approve an external reviewer."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The exact schema the review skills' resolver accepts. A missing, unknown or malformed key makes them
# ignore the file, and a missing file makes them pick an external CLI that receives the diff.
HOST_ONLY = {
    "mode": "host-only",
    "claude": {"model": None, "effort": "high"},
    "codex": {"model": None, "effort": "high"},
    "cursor": {"model": None},
    "omp": {"model": None, "effort": "high"},
}


@pytest.mark.unit
def test_code_review_runs_on_the_host_only() -> None:
    assert json.loads((ROOT / "docs/agents/cross-model.json").read_text()) == HOST_ONLY
