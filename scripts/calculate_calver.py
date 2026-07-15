"""Calculate a collision-safe daily CalVer from local release tags."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence

CALVER_PATTERN = re.compile(
    r"^(?P<release_date>[0-9]{2}\.[0-9]{2}\.[0-9]{2})(?:\.(?P<revision>[1-9][0-9]*))?$"
)


class CalVerError(RuntimeError):
    """Raised when a release version cannot be calculated or validated safely."""


def validate_calver(version: str) -> str:
    """Return a valid ``YY.MM.DD[.N]`` CalVer or raise ``CalVerError``."""
    match = CALVER_PATTERN.fullmatch(version)
    if match is None:
        raise CalVerError(f"CalVer must use YY.MM.DD or YY.MM.DD.N with N >= 1: {version!r}")

    try:
        dt.datetime.strptime(match.group("release_date"), "%y.%m.%d")
    except ValueError as exc:
        raise CalVerError(f"CalVer contains an invalid YY.MM.DD date: {version!r}") from exc

    return version


def calculate_next_calver(tags: Iterable[str], *, release_date: dt.date) -> str:
    """Return the next ``YY.MM.DD[.N]`` CalVer for ``release_date``."""
    base_version = release_date.strftime("%y.%m.%d")
    base_tag = f"v{base_version}"
    revision_pattern = re.compile(rf"^{re.escape(base_tag)}\.(?P<revision>[0-9]+)$")
    release_exists = False
    current_revision = 0

    for raw_tag in tags:
        tag = raw_tag.strip()
        if tag == base_tag:
            release_exists = True
            continue

        match = revision_pattern.fullmatch(tag)
        if match is not None:
            release_exists = True
            current_revision = max(current_revision, int(match.group("revision")))

    if not release_exists:
        return base_version
    return f"{base_version}.{current_revision + 1}"


def _git_executable() -> str:
    """Return the absolute Git executable path or fail closed."""
    git = shutil.which("git")
    if git is None:
        raise CalVerError("git executable not found")
    return git


def _local_release_tags(release_date: dt.date) -> tuple[str, ...]:
    """Read this date's release tags from the fully fetched local repository."""
    base_version = release_date.strftime("%y.%m.%d")
    try:
        result = subprocess.run(  # noqa: S603 - executable is resolved and arguments are fixed
            [_git_executable(), "tag", "--list", f"v{base_version}*"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CalVerError("unable to inspect local release tags") from exc
    return tuple(result.stdout.splitlines())


def get_calver(*, release_date: dt.date | None = None) -> str:
    """Return the next UTC daily CalVer using fully fetched local release tags."""
    selected_date = release_date or dt.datetime.now(dt.UTC).date()
    return calculate_next_calver(_local_release_tags(selected_date), release_date=selected_date)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse the optional maintainer-selected backfill version."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requested", help="Validated YY.MM.DD[.N] override")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the selected CalVer, failing closed on invalid input or Git errors."""
    args = _parse_args(argv)
    try:
        version = validate_calver(args.requested) if args.requested else get_calver()
    except CalVerError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    sys.stdout.write(f"{version}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
