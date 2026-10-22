#!/usr/bin/env python3
# ruff: noqa: S603, S607
"""Validate and assemble per-pull-request changelog fragments."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security", "Docs", "Tests")
FRAGMENT_NAME = re.compile(r"pr-([1-9][0-9]*)\.md\Z")
UNRELEASED_HEADING = "## [Unreleased]"


@dataclass(frozen=True, slots=True)
class ChangelogFragment:
    """A validated fragment and its release-note sections."""

    path: Path
    number: int
    sections: dict[str, str]


def _store_section(
    sections: dict[str, str],
    category: str,
    lines: list[str],
    source: str,
) -> None:
    """Store a section after confirming it contains at least one bullet."""
    body = "\n".join(lines).strip()
    if not any(line.startswith("- ") for line in body.splitlines()):
        raise ValueError(f"{source}: section '### {category}' must contain a bullet")
    sections[category] = body


def _append_content_line(
    line: str,
    line_number: int,
    source: str,
    category: str | None,
    section_lines: list[str],
) -> None:
    """Validate and append a non-heading section line."""
    if not line.strip():
        if category is not None:
            section_lines.append("")
        return
    if category is None:
        raise ValueError(f"{source}:{line_number}: content must follow a category heading")
    if line.startswith("- ") or line[0].isspace():
        section_lines.append(line)
        return
    raise ValueError(f"{source}:{line_number}: changelog entries must be Markdown bullets")


def parse_sections(content: str, source: str) -> dict[str, str]:
    """Parse category headings and bullet entries from changelog Markdown."""
    sections: dict[str, str] = {}
    current_category: str | None = None
    current_lines: list[str] = []

    for line_number, line in enumerate(content.splitlines(), start=1):
        if line.startswith("### "):
            if current_category is not None:
                _store_section(sections, current_category, current_lines, source)

            category = line.removeprefix("### ").strip()
            if category not in CATEGORIES:
                raise ValueError(f"{source}:{line_number}: unsupported changelog category")
            if category in sections:
                raise ValueError(f"{source}:{line_number}: duplicate category '{category}'")

            current_category = category
            current_lines = []
        else:
            _append_content_line(line, line_number, source, current_category, current_lines)

    if current_category is not None:
        _store_section(sections, current_category, current_lines, source)
    if not sections and content.strip():
        raise ValueError(f"{source}: add a supported category heading and a bullet")
    return sections


def extract_unreleased(content: str) -> str:
    """Return the Markdown body between the Unreleased heading and the next release."""
    lines = content.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.startswith(UNRELEASED_HEADING)),
        None,
    )
    if start is None:
        raise ValueError(f"Changelog has no {UNRELEASED_HEADING} heading")

    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith("## [")),
        len(lines),
    )
    return "\n".join(lines[start + 1 : end]).strip()


def load_fragments(fragment_dir: Path) -> list[ChangelogFragment]:
    """Load, validate, and numerically order all per-PR fragments."""
    if fragment_dir.is_symlink():
        raise ValueError(f"{fragment_dir}: fragment directory cannot be a symlink")
    if not fragment_dir.exists():
        return []
    if not fragment_dir.is_dir():
        raise ValueError(f"{fragment_dir}: expected a directory")

    fragments: list[ChangelogFragment] = []
    for path in sorted(fragment_dir.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != ".md":
            raise ValueError(f"{path}: only regular Markdown fragment files are allowed")
        match = FRAGMENT_NAME.fullmatch(path.name)
        if match is None:
            raise ValueError(f"{path}: name must use the format 'pr-<number>.md'")

        content = path.read_text(encoding="utf-8")
        sections = parse_sections(content, str(path))
        if not sections:
            raise ValueError(f"{path}: fragment must contain a category and a release-note bullet")
        fragments.append(
            ChangelogFragment(path=path, number=int(match.group(1)), sections=sections)
        )

    return sorted(fragments, key=lambda fragment: fragment.number)


def render_sections(section_maps: Sequence[dict[str, str]]) -> str:
    """Combine fragment sections in stable category and pull-request order."""
    grouped: dict[str, list[str]] = {category: [] for category in CATEGORIES}
    for sections in section_maps:
        for category, body in sections.items():
            grouped[category].append(body)

    rendered = [
        f"### {category}\n\n" + "\n\n".join(grouped[category])
        for category in CATEGORIES
        if grouped[category]
    ]
    return "\n\n".join(rendered)


def collect_changelog(changelog: Path, fragment_dir: Path) -> str:
    """Assemble legacy Unreleased notes and validated fragments for a release."""
    legacy_notes = extract_unreleased(changelog.read_text(encoding="utf-8"))
    section_maps = []
    if legacy_notes:
        section_maps.append(parse_sections(legacy_notes, str(changelog)))
    section_maps.extend(fragment.sections for fragment in load_fragments(fragment_dir))
    return render_sections(section_maps)


def changed_fragment_paths(
    base: str,
    fragment_dir: Path,
    *,
    cwd: Path | None = None,
) -> list[str]:
    """Return added or modified fragment paths in a pull request."""
    if re.fullmatch(r"[0-9a-f]{40}", base) is None:
        raise ValueError("Base must be a full lowercase Git commit SHA")
    # Git receives a fixed argument vector and validated SHA; no shell parses input values.
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=AM",
            f"{base}...HEAD",
            "--",
            fragment_dir.as_posix(),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return [path for path in result.stdout.splitlines() if path]


def validate_pull_request_fragment(
    changed_paths: Sequence[str],
    pull_request_number: int,
    fragment_dir: Path,
) -> None:
    """Require a pull request to change only its uniquely named fragment."""
    if pull_request_number < 1:
        raise ValueError("Pull request number must be greater than zero")

    expected = (fragment_dir / f"pr-{pull_request_number}.md").as_posix()
    changed = set(changed_paths)
    if expected not in changed:
        raise ValueError(f"Add {expected} with this pull request's release note")

    unexpected = changed - {expected}
    if unexpected:
        paths = ", ".join(sorted(unexpected))
        raise ValueError(f"Do not modify another pull request's changelog fragment: {paths}")


def clear_fragments(fragment_dir: Path) -> int:
    """Remove validated fragments after their notes are promoted to CHANGELOG.md."""
    fragments = load_fragments(fragment_dir)
    for fragment in fragments:
        fragment.path.unlink()
    return len(fragments)


def main(argv: Sequence[str] | None = None) -> int:
    """Run fragment validation, collection, or cleanup."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate_parser = commands.add_parser("validate", help="validate all fragments")
    validate_parser.add_argument("--fragment-dir", type=Path, default=Path("changelog.d"))
    validate_parser.add_argument("--base")
    validate_parser.add_argument("--pull-request-number", type=int)

    collect_parser = commands.add_parser("collect", help="assemble release notes")
    collect_parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    collect_parser.add_argument("--fragment-dir", type=Path, default=Path("changelog.d"))

    clear_parser = commands.add_parser("clear", help="remove promoted fragments")
    clear_parser.add_argument("--fragment-dir", type=Path, default=Path("changelog.d"))

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            if (args.base is None) != (args.pull_request_number is None):
                raise ValueError("--base and --pull-request-number must be used together")
            fragments = load_fragments(args.fragment_dir)
            if args.base is not None:
                changed = changed_fragment_paths(args.base, args.fragment_dir)
                validate_pull_request_fragment(
                    changed,
                    args.pull_request_number,
                    args.fragment_dir,
                )
            sys.stdout.write(f"Validated {len(fragments)} changelog fragment(s).\n")
        elif args.command == "collect":
            notes = collect_changelog(args.changelog, args.fragment_dir)
            if notes:
                sys.stdout.write(f"{notes}\n")
        else:
            count = clear_fragments(args.fragment_dir)
            sys.stdout.write(f"Removed {count} promoted changelog fragment(s).\n")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.stderr.write(f"changelog fragments: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
