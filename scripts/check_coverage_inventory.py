"""Verify that coverage data accounts for every distributable Python module."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from coverage import Coverage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "micboard"


def distributable_source_files() -> set[Path]:
    """Return non-migration Python modules shipped in the micboard package."""
    return {
        path.resolve()
        for path in PACKAGE_ROOT.rglob("*.py")
        if "migrations" not in path.parts and "fuzzers" not in path.parts
    }


def measured_source_files(data_file: Path) -> set[Path]:
    """Return normalized files recorded in one coverage data file."""
    coverage = Coverage(data_file=str(data_file))
    coverage.load()
    return {
        (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
        for filename in coverage.get_data().measured_files()
        if (path := Path(filename)).suffix == ".py"
    }


def main() -> int:
    """Report unmeasured package modules and return a failing status when found."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "data_file",
        nargs="?",
        type=Path,
        default=PROJECT_ROOT / ".coverage",
        help="coverage data file (default: .coverage)",
    )
    args = parser.parse_args()

    missing = sorted(distributable_source_files() - measured_source_files(args.data_file))
    if missing:
        missing_lines = "\n".join(f"  {path.relative_to(PROJECT_ROOT)}" for path in missing)
        sys.stderr.write(f"Coverage omitted distributable Python modules:\n{missing_lines}\n")
        return 1

    sys.stdout.write(
        f"Coverage inventory includes {len(distributable_source_files())} Python modules.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
