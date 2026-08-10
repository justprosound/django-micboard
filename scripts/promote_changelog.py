#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

UNRELEASED_HEADING = "## [Unreleased]"
RELEASE_HEADING_PREFIX = "## ["


@dataclass(frozen=True, slots=True)
class ReleaseSection:
    version: str
    release_date: str
    notes: str


def promote_changelog(content: str, section: ReleaseSection) -> str:
    lines = content.splitlines()
    unreleased_index = lines.index(UNRELEASED_HEADING)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("changelog", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--notes-file", required=True, type=Path)
    args = parser.parse_args()

    section = ReleaseSection(
        version=args.version,
        release_date=args.date,
        notes=args.notes_file.read_text(),
    )
    args.changelog.write_text(promote_changelog(args.changelog.read_text(), section))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
