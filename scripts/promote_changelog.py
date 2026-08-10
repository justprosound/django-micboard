#!/usr/bin/env python3
"""Promote unreleased changelog notes into a versioned release section."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

UNRELEASED_HEADING = "## [Unreleased]"
RELEASE_HEADING_PREFIX = "## ["


@dataclass(frozen=True, slots=True)
class ReleaseSection:
    """Container for versioned release metadata and notes."""

    version: str
    release_date: str
    notes: str


def promote_changelog(content: str, section: ReleaseSection) -> str:
    """Insert a new versioned release section into the changelog content."""
    lines = content.splitlines()
    unreleased_index = next(
        (index for index, line in enumerate(lines) if line.startswith(UNRELEASED_HEADING)),
        None,
    )
    if unreleased_index is None:
        raise ValueError(f"Changelog has no {UNRELEASED_HEADING} heading")
    next_release_index = next(
        (
            index
            for index in range(unreleased_index + 1, len(lines))
            if lines[index].startswith(RELEASE_HEADING_PREFIX)
        ),
        len(lines),
    )
    notes = section.notes.strip()
    release_lines = [
        "",
        f"## [{section.version}] - {section.release_date}",
        "",
        *notes.splitlines(),
        "",
    ]
    promoted = [*lines[: unreleased_index + 1], *release_lines, *lines[next_release_index:]]
    return "\n".join(promoted).rstrip() + "\n"


def main() -> int:
    """CLI entry point for promoting unreleased changelog notes."""
    parser = argparse.ArgumentParser()
    parser.add_argument("changelog", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--notes-file", required=True, type=Path)
    args = parser.parse_args()

    section = ReleaseSection(
        version=args.version,
        release_date=args.date,
        notes=args.notes_file.read_text(encoding="utf-8"),
    )
    args.changelog.write_text(
        promote_changelog(args.changelog.read_text(encoding="utf-8"), section),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
