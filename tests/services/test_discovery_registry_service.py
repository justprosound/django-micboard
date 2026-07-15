"""Discovery registry trigger-policy contracts."""

from types import SimpleNamespace

import pytest

from micboard.services.discovery.registry_service import (
    discovery_manufacturer_for_config,
    discovery_manufacturer_for_entry,
)


@pytest.mark.parametrize("key", ["SHURE_DISCOVERY_CIDRS", "SHURE_DISCOVERY_FQDNS"])
def test_discovery_config_keys_return_their_manufacturer(key: str) -> None:
    """Only discovery source settings schedule a manufacturer rescan."""
    config = SimpleNamespace(key=key, manufacturer=SimpleNamespace(pk=17))

    assert discovery_manufacturer_for_config(config) == 17


def test_unrelated_or_global_config_does_not_schedule_discovery() -> None:
    """Global and unrelated settings remain side-effect free."""
    assert (
        discovery_manufacturer_for_config(
            SimpleNamespace(key="SHURE_DISCOVERY_CIDRS", manufacturer=None)
        )
        is None
    )
    assert (
        discovery_manufacturer_for_config(
            SimpleNamespace(key="BATTERY_WARNING_LEVEL", manufacturer=SimpleNamespace(pk=17))
        )
        is None
    )


def test_registry_entry_returns_persisted_manufacturer_identity() -> None:
    """CIDR and FQDN entries already carry the exact rescan owner."""
    assert discovery_manufacturer_for_entry(SimpleNamespace(manufacturer_id=23)) == 23
