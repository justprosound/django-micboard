#!/usr/bin/env python3
# ruff: noqa: S603, S607, T201
"""Verify that the generated documentation requirements match ``uv.lock``."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = ROOT / "docs" / "requirements.txt"
EXPORT_ARGUMENTS = (
    "export",
    "--locked",
    "--no-dev",
    "--extra",
    "docs",
    "--no-emit-project",
)
REGENERATE_COMMAND = ("uv", *EXPORT_ARGUMENTS, "--output-file", "docs/requirements.txt")
RequirementKey = tuple[str, str, str]


def parse_requirements(content: str) -> dict[RequirementKey, set[str]]:
    """Parse requirement identities and hashes without depending on export formatting."""
    requirements: dict[RequirementKey, set[str]] = {}
    current: RequirementKey | None = None
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("--hash="):
            if current is None:
                raise ValueError("requirement hash appears before a requirement")
            requirements[current].add(stripped.removeprefix("--hash=").rstrip(" \\"))
            continue
        requirement = Requirement(stripped.rstrip(" \\"))
        current = (
            canonicalize_name(requirement.name),
            str(requirement.specifier),
            str(requirement.marker or ""),
        )
        requirements.setdefault(current, set())
    return requirements


def exported_requirements() -> dict[RequirementKey, set[str]]:
    """Return normalized requirements and hashes for the locked docs extra."""
    result = subprocess.run(
        ("uv", *EXPORT_ARGUMENTS, "--no-header", "--no-annotate"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_requirements(result.stdout)


def validation_errors(content: str) -> list[str]:
    """Return semantic lock/export mismatches for the committed requirements file."""
    errors: list[str] = []
    actual = parse_requirements(content)
    expected = exported_requirements()
    if actual.keys() != expected.keys():
        missing = sorted(expected.keys() - actual.keys())
        unexpected = sorted(actual.keys() - expected.keys())
        if missing:
            errors.append(f"missing requirements: {missing}")
        if unexpected:
            errors.append(f"unexpected requirements: {unexpected}")

    for key in actual.keys() & expected.keys():
        name, specifier, _marker = key
        missing_hashes = expected[key] - actual[key]
        unexpected_hashes = actual[key] - expected[key]
        if missing_hashes:
            errors.append(f"{name}{specifier}: missing {len(missing_hashes)} exported hash(es)")
        if unexpected_hashes:
            errors.append(
                f"{name}{specifier}: contains {len(unexpected_hashes)} unexpected hash(es)"
            )
    return errors


def main() -> int:
    """Return a failure when the committed export does not match the lockfile."""
    errors = validation_errors(REQUIREMENTS_PATH.read_text())
    if not errors:
        return 0

    print("docs/requirements.txt is stale; regenerate it with:")
    print(f"  {shlex.join(REGENERATE_COMMAND)}")
    for error in errors:
        print(f"  - {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
