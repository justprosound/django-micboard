"""Normalize source-distribution metadata for byte-reproducible release archives."""

from __future__ import annotations

import argparse
import copy
import gzip
import os
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path


class SdistNormalizationError(RuntimeError):
    """Raised when a source archive cannot be normalized safely."""


def normalize_sdist(path: Path, *, source_date_epoch: int) -> None:
    """Rewrite one ``.tar.gz`` with stable ordering, ownership, timestamps, and gzip metadata."""
    if source_date_epoch < 0:
        raise SdistNormalizationError("SOURCE_DATE_EPOCH must be a non-negative integer")
    if not path.is_file():
        raise SdistNormalizationError(f"source distribution does not exist: {path}")

    original_mode = path.stat().st_mode
    temporary_path: Path | None = None
    try:
        with (
            tarfile.open(path, mode="r:gz") as source_archive,
            tempfile.NamedTemporaryFile(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as raw_archive,
        ):
            temporary_path = Path(raw_archive.name)
            with (
                gzip.GzipFile(
                    fileobj=raw_archive,
                    mode="wb",
                    filename="",
                    mtime=source_date_epoch,
                    compresslevel=9,
                ) as compressed_archive,
                tarfile.open(
                    fileobj=compressed_archive,
                    mode="w",
                    format=tarfile.PAX_FORMAT,
                ) as normalized_archive,
            ):
                for source_member in sorted(
                    source_archive.getmembers(),
                    key=lambda member: member.name,
                ):
                    member = copy.copy(source_member)
                    member.mtime = source_date_epoch
                    member.uid = 0
                    member.gid = 0
                    member.uname = ""
                    member.gname = ""
                    member.pax_headers = {}
                    content = (
                        source_archive.extractfile(source_member)
                        if source_member.isfile()
                        else None
                    )
                    try:
                        normalized_archive.addfile(member, content)
                    finally:
                        if content is not None:
                            content.close()

        if temporary_path is None:
            raise SdistNormalizationError(f"unable to create normalized archive for {path}")
        temporary_path.chmod(original_mode)
        os.replace(temporary_path, path)
        temporary_path = None
    except (OSError, tarfile.TarError) as exc:
        raise SdistNormalizationError(f"unable to normalize source distribution: {path}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _source_date_epoch(value: str | None) -> int:
    """Parse the required release timestamp."""
    if value is None:
        raise SdistNormalizationError("SOURCE_DATE_EPOCH is required")
    try:
        return int(value)
    except ValueError as exc:
        raise SdistNormalizationError("SOURCE_DATE_EPOCH must be a non-negative integer") from exc


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse source archives and their reproducible timestamp."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument(
        "--source-date-epoch",
        default=os.environ.get("SOURCE_DATE_EPOCH"),
        help="Unix timestamp; defaults to SOURCE_DATE_EPOCH",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Normalize each requested source archive or report a closed failure."""
    args = _parse_args(argv)
    try:
        source_date_epoch = _source_date_epoch(args.source_date_epoch)
        for archive in args.archives:
            normalize_sdist(archive, source_date_epoch=source_date_epoch)
    except SdistNormalizationError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
