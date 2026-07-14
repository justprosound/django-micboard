"""Regression tests for static import direction and cycle detection."""

from __future__ import annotations

from pathlib import Path

from scripts.check_import_architecture import analyze_import_architecture, format_report


def _write_module(package: Path, relative_path: str, source: str = "") -> None:
    path = package / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_checker_resolves_relative_imports_and_reports_cycle(tmp_path: Path) -> None:
    package = tmp_path / "sample"
    _write_module(package, "__init__.py")
    _write_module(package, "alpha.py", "from .beta import Beta\n")
    _write_module(package, "beta.py", "from .alpha import Alpha\n")

    report = analyze_import_architecture(package)

    assert report.cycles == (("sample.alpha", "sample.beta"),)
    formatted = format_report(report)
    assert f"{package / 'alpha.py'}:1: sample.alpha -> sample.beta" in formatted
    assert f"{package / 'beta.py'}:1: sample.beta -> sample.alpha" in formatted


def test_checker_reports_forbidden_edges_with_source_locations(tmp_path: Path) -> None:
    package = tmp_path / "sample"
    _write_module(package, "__init__.py")
    _write_module(package, "apps.py")
    _write_module(package, "models/__init__.py")
    _write_module(package, "models/device.py", "from sample.services import worker\n")
    _write_module(package, "services/__init__.py")
    _write_module(
        package,
        "services/worker.py",
        "from sample import apps\nfrom sample.tasks import job\n",
    )
    _write_module(package, "tasks/__init__.py")
    _write_module(package, "tasks/job.py")

    report = analyze_import_architecture(package)

    violations = {
        (edge.source, edge.target, edge.path.name, edge.line) for edge in report.forbidden_edges
    }
    assert violations == {
        ("sample.models.device", "sample.services", "device.py", 1),
        ("sample.models.device", "sample.services.worker", "device.py", 1),
        ("sample.services.worker", "sample.apps", "worker.py", 1),
        ("sample.services.worker", "sample.tasks", "worker.py", 2),
        ("sample.services.worker", "sample.tasks.job", "worker.py", 2),
    }


def test_micboard_import_architecture_is_acyclic() -> None:
    report = analyze_import_architecture(Path("micboard"))

    assert report.is_valid, format_report(report)
