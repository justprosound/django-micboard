"""Band-plan fixture lookup and detection contracts."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from micboard.models import band_plans


def test_loader_reads_packaged_fixture() -> None:
    """Installed package resources provide the same registry used in development."""
    loaded = band_plans._load_band_plans()

    assert "shure" in loaded
    assert loaded["shure"]["g50"]["min_mhz"] == 470


def test_loader_handles_missing_optional_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture support degrades to an empty registry when YAML is unavailable."""
    monkeypatch.setattr(band_plans, "HAS_YAML", False)

    assert band_plans._load_band_plans() == {}


def test_loader_normalizes_empty_yaml_document(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty fixture is represented by an empty mapping, never None."""
    monkeypatch.setattr(band_plans.yaml, "safe_load", Mock(return_value=None))

    assert band_plans._load_band_plans() == {}


def test_loader_contains_resource_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing packaged resource cannot prevent application startup."""
    monkeypatch.setattr(
        band_plans.importlib.resources,
        "files",
        Mock(side_effect=FileNotFoundError("fixture missing")),
    )

    assert band_plans._load_band_plans() == {}


@pytest.mark.parametrize(
    ("manufacturer", "key", "expected"),
    [
        (None, "g50", None),
        ("shure", None, None),
        ("missing", "g50", None),
        ("SHURE", "G50", "G50 (470-534 MHz)"),
        ("shure", "G50", "G50 (470-534 MHz)"),
    ],
)
def test_band_plan_lookup_normalizes_identity(
    manufacturer: str | None,
    key: str | None,
    expected: str | None,
) -> None:
    """Manufacturer and plan identity are case-insensitive and optional-safe."""
    plan = band_plans.get_band_plan(manufacturer=manufacturer, band_plan_key=key)

    assert (plan or {}).get("name") == expected


def test_band_plan_lookup_normalizes_spaces_and_hyphens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Human and machine key separators select the same registry entry."""
    monkeypatch.setattr(
        band_plans,
        "BAND_PLAN_SPECIFICATIONS",
        {"vendor": {"wide_band": {"name": "Wide Band"}}},
    )

    assert band_plans.get_band_plan(
        manufacturer="vendor",
        band_plan_key="Wide-Band",
    ) == {"name": "Wide Band"}


def test_available_band_plans_handles_missing_and_registered_manufacturers() -> None:
    """Choice consumers receive stable empty or key-label pairs."""
    assert band_plans.get_available_band_plans(manufacturer=None) == []
    assert band_plans.get_available_band_plans(manufacturer="missing") == []

    available = band_plans.get_available_band_plans(manufacturer="SHURE")
    assert ("g50", "G50 (470-534 MHz)") in available


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("G50 (470-534 MHz)", {"min_mhz": 470.0, "max_mhz": 534.0}),
        ("Aw+ 470.5 - 558.25MHz", {"min_mhz": 470.5, "max_mhz": 558.25}),
        ("No frequencies", None),
    ],
)
def test_parse_band_plan_name_extracts_frequency_range(
    name: str,
    expected: dict[str, float] | None,
) -> None:
    """Display labels expose numeric frequency bounds when present."""
    assert band_plans.parse_band_plan_from_name(name=name) == expected


def test_band_key_and_extraction_helpers_normalize_api_values() -> None:
    """Detection helpers normalize punctuation, codes, and numeric ranges."""
    assert band_plans._normalize_band_key("Aw+ (470-558)") == "aw+_470_558"
    assert band_plans._extract_band_code("G50 (470-534)") == "g50"
    assert band_plans._extract_band_code("---") is None
    assert band_plans._extract_freq_range("470.5 - 558.25 MHz") == (470.5, 558.25)
    assert band_plans._extract_freq_range("no range") is None


def _detection_registry() -> dict[str, dict[str, dict]]:
    return {
        "vendor": {
            "g50": {"name": "G50", "min_mhz": 400.0, "max_mhz": 450.0},
            "range": {"name": "Range Plan", "min_mhz": 470.0, "max_mhz": 534.0},
            "foo_bar": {"name": "Foo Bar", "min_mhz": 500.0, "max_mhz": 510.0},
            "nameless": {"min_mhz": 600.0, "max_mhz": 610.0},
        }
    }


def test_detection_helpers_cover_match_and_no_match_strategies() -> None:
    """Code, frequency, and partial-key helpers each remain independently usable."""
    plans = _detection_registry()["vendor"]

    assert band_plans._find_plan_by_code(plans, "G50 extra") == "G50"
    assert band_plans._find_plan_by_code(plans, "---") is None
    assert band_plans._find_plan_by_code(plans, "missing") is None
    assert band_plans._find_plan_by_code(plans, "nameless") is None

    assert band_plans._find_plan_by_frequency_range(plans, "470-534 MHz") == "Range Plan"
    assert band_plans._find_plan_by_frequency_range(plans, "no range") is None
    assert band_plans._find_plan_by_frequency_range(plans, "700-800 MHz") is None

    assert band_plans._find_plan_by_partial_key(plans, "Foo Bar extended") == "Foo Bar"
    assert band_plans._find_plan_by_partial_key(plans, "unrelated") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("   ", None),
        ("G50", "G50"),
        ("G50 extra", "G50"),
        ("470-534 MHz", "Range Plan"),
        ("Foo Bar extended", "Foo Bar"),
        ("unrelated", None),
    ],
)
def test_api_band_detection_uses_ordered_strategies(
    value: str | None,
    expected: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API values progress from exact to code, range, and partial matching."""
    monkeypatch.setattr(
        band_plans,
        "BAND_PLAN_SPECIFICATIONS",
        _detection_registry(),
    )

    assert (
        band_plans.detect_band_plan_from_api_string(
            api_band_value=value,
            manufacturer="vendor",
        )
        == expected
    )


def test_api_band_detection_defaults_to_shure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing manufacturer retains the documented Shure default."""
    monkeypatch.setattr(
        band_plans,
        "BAND_PLAN_SPECIFICATIONS",
        {"shure": {"g50": {"name": "G50"}}},
    )

    assert (
        band_plans.detect_band_plan_from_api_string(
            api_band_value="g50",
            manufacturer=None,
        )
        == "G50"
    )


@pytest.mark.parametrize(
    ("manufacturer", "model", "expected"),
    [
        (None, "ULXD4Q-G50", None),
        ("shure", None, None),
        ("shure", "ULXD4Q-G50", "G50 (470-534 MHz)"),
        ("shure", "G50 receiver", "G50 (470-534 MHz)"),
        ("shure", "receiver", None),
        ("shure", "G999 receiver", None),
    ],
)
def test_model_code_detection_finds_embedded_band_hint(
    manufacturer: str | None,
    model: str | None,
    expected: str | None,
) -> None:
    """Model suffixes and prefixes select registered bands without false defaults."""
    assert (
        band_plans.get_band_plan_from_model_code(
            manufacturer=manufacturer,
            model=model,
        )
        == expected
    )
