#!/usr/bin/env python3
# ruff: noqa: T201
"""Validate that built wheels contain the complete reusable Django app."""

from __future__ import annotations

import argparse
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

RESOURCE_DIRECTORIES = frozenset({"fixtures", "migrations", "static", "templates"})
EXCLUDED_DIRECTORIES = frozenset({"__pycache__", "tests"})
FORBIDDEN_PREFIXES = ("example_project/", "scripts/", "tests/", "micboard/tests/")


def source_members(project_root: Path) -> set[str]:
    """Return source files that every distributable wheel must contain."""
    package_root = project_root / "micboard"
    members: set[str] = set()

    for path in package_root.rglob("*"):
        if not path.is_file():
            continue

        relative = path.relative_to(project_root)
        if EXCLUDED_DIRECTORIES.intersection(relative.parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if path.suffix == ".py" or RESOURCE_DIRECTORIES.intersection(relative.parts):
            members.add(relative.as_posix())

    return members


def validate_wheel(wheel_path: Path, project_root: Path) -> list[str]:
    """Return validation errors for one wheel, or an empty list when valid."""
    expected = source_members(project_root)

    try:
        with ZipFile(wheel_path) as wheel:
            members = {name for name in wheel.namelist() if not name.endswith("/")}
            metadata_names = [name for name in members if name.endswith(".dist-info/METADATA")]
            metadata = (
                BytesParser().parsebytes(wheel.read(metadata_names[0]))
                if len(metadata_names) == 1
                else None
            )
    except (BadZipFile, OSError) as exc:
        return [f"cannot read wheel: {exc}"]

    errors: list[str] = []
    missing = sorted(expected - members)
    if missing:
        errors.append("missing source files:\n  " + "\n  ".join(missing))

    packaged_app_members = {member for member in members if member.startswith("micboard/")}
    unexpected = sorted(packaged_app_members - expected)
    if unexpected:
        errors.append("contains stale or undeclared app files:\n  " + "\n  ".join(unexpected))

    forbidden = sorted(
        member
        for member in members
        if member.startswith(FORBIDDEN_PREFIXES)
        or "__pycache__" in PurePosixPath(member).parts
        or member.endswith((".pyc", ".pyo"))
    )
    if forbidden:
        errors.append("contains development artifacts:\n  " + "\n  ".join(forbidden))

    if metadata is None:
        errors.append("expected exactly one .dist-info/METADATA file")
    else:
        if metadata.get("Requires-Python") != ">=3.13":
            errors.append(
                f"Requires-Python is {metadata.get('Requires-Python')!r}; expected '>=3.13'"
            )
        if metadata.get("License-Expression") != "AGPL-3.0-or-later":
            errors.append(
                "License-Expression is "
                f"{metadata.get('License-Expression')!r}; expected 'AGPL-3.0-or-later'"
            )

    license_files = [name for name in members if name.endswith(".dist-info/licenses/LICENSE")]
    if len(license_files) != 1:
        errors.append("expected exactly one packaged .dist-info/licenses/LICENSE file")

    return errors


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheels", nargs="+", type=Path, help="wheel files to validate")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root containing the micboard package",
    )
    return parser.parse_args()


def main() -> int:
    """Validate all requested wheels and return a process exit status."""
    args = parse_args()
    failed = False

    for wheel_path in args.wheels:
        errors = validate_wheel(wheel_path.resolve(), args.project_root.resolve())
        if errors:
            failed = True
            print(f"FAIL {wheel_path}")
            for error in errors:
                print(f"  {error}")
        else:
            print(f"OK {wheel_path}: reusable-app contents complete")

    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
