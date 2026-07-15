"""Tests for deterministic source-distribution normalization."""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

from scripts.normalize_sdist import normalize_sdist


def _write_sdist(path: Path, *, timestamp: int, owner: int) -> None:
    """Write equivalent source content with deliberately different archive metadata."""
    with (
        path.open("wb") as raw_archive,
        gzip.GzipFile(fileobj=raw_archive, mode="wb", mtime=timestamp) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        payload = b"release contents\n"
        member = tarfile.TarInfo("django_micboard-26.7.15/README.md")
        member.size = len(payload)
        member.mtime = timestamp
        member.uid = owner
        member.gid = owner
        member.uname = f"owner-{owner}"
        member.gname = f"group-{owner}"
        archive.addfile(member, io.BytesIO(payload))


def test_normalize_sdist_produces_identical_bytes_and_preserves_content(tmp_path: Path) -> None:
    """Build time and runner identity must not alter a released source archive."""
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    release_epoch = 1_784_141_696
    _write_sdist(first, timestamp=release_epoch + 10, owner=1000)
    _write_sdist(second, timestamp=release_epoch + 20, owner=2000)

    normalize_sdist(first, source_date_epoch=release_epoch)
    normalize_sdist(second, source_date_epoch=release_epoch)

    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first, mode="r:gz") as archive:
        member = archive.getmember("django_micboard-26.7.15/README.md")
        extracted = archive.extractfile(member)
        assert extracted is not None
        assert extracted.read() == b"release contents\n"
        assert member.mtime == release_epoch
        assert member.uid == member.gid == 0
        assert member.uname == member.gname == ""
