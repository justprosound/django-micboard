"""Public documentation path contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_context_references_the_live_middleware_module() -> None:
    """The architecture map must point contributors at an importable source file."""
    context = (ROOT / "docs/development/context.md").read_text()

    assert "`micboard/multitenancy/middleware.py`" in context
    assert "`micboard/middleware.py`" not in context
    assert (ROOT / "micboard/multitenancy/middleware.py").is_file()


def test_integration_validation_commands_reference_live_tests() -> None:
    """Copyable integration commands cannot silently retain deleted test paths."""
    guide = (ROOT / "docs/integration/integration-references.md").read_text()
    expected_paths = (
        "tests/test_manufacturer_plugin_resolution.py",
        "tests/test_polling_api_service.py",
        "tests/tasks/sync/test_polling_tasks.py",
        "tests/services/manufacturer/test_sync_service.py",
        "tests/test_poll_devices_reporting.py",
    )

    assert "tests/test_polling_runtime.py" not in guide
    for relative_path in expected_paths:
        assert relative_path in guide
        assert (ROOT / relative_path).is_file()
