"""Regression tests for the generated documentation requirements guard."""

from __future__ import annotations

import pytest

import scripts.check_docs_requirements as requirements_check

LOCKED_HASH = f"sha256:{'a' * 64}"
STALE_HASH = f"sha256:{'b' * 64}"
REQUIREMENT_KEY = ("demo-package", "==1.0", 'sys_platform == "linux"')


def requirement_export(artifact_hash: str) -> str:
    """Return a representative multiline uv requirements entry."""
    return (
        "# generated header\n"
        "demo_package==1.0 ; sys_platform == 'linux' \\\n"
        f"    --hash={artifact_hash}\n"
        "    # via example\n"
    )


def test_parse_requirements_normalizes_names_markers_and_formatting() -> None:
    assert requirements_check.parse_requirements(requirement_export(LOCKED_HASH)) == {
        REQUIREMENT_KEY: {LOCKED_HASH}
    }


def test_validation_requires_the_complete_exported_hash_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        requirements_check,
        "exported_requirements",
        lambda: {REQUIREMENT_KEY: {LOCKED_HASH}},
    )

    assert requirements_check.validation_errors(requirement_export(LOCKED_HASH)) == []
    assert requirements_check.validation_errors(requirement_export(STALE_HASH)) == [
        "demo-package==1.0: missing 1 exported hash(es)",
        "demo-package==1.0: contains 1 unexpected hash(es)",
    ]
    assert requirements_check.validation_errors(
        requirement_export("").replace("--hash=\n", "")
    ) == [
        "demo-package==1.0: missing 1 exported hash(es)",
    ]


def test_validation_rejects_indented_unexpected_requirements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        requirements_check,
        "exported_requirements",
        lambda: {REQUIREMENT_KEY: {LOCKED_HASH}},
    )
    content = requirement_export(LOCKED_HASH) + "    unexpected_package==2.0\n"

    assert requirements_check.validation_errors(content) == [
        "unexpected requirements: [('unexpected-package', '==2.0', '')]"
    ]
