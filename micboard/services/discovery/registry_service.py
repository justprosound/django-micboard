"""Service functions for discovery registry model persistence.

Provides save and delete delegation for MicboardConfig, DiscoveryCIDR,
and DiscoveryFQDN models, separated from the model layer per ADR-002.
"""

from __future__ import annotations


def save_micboard_config(config, *args, **kwargs) -> None:
    """Save MicboardConfig and trigger discovery scan if Shure config changed."""
    from micboard.models.discovery.registry import MicboardConfig as _MicboardConfig

    super(_MicboardConfig, config).save(*args, **kwargs)

    if config.manufacturer and config.key in (
        "SHURE_DISCOVERY_CIDRS",
        "SHURE_DISCOVERY_FQDNS",
    ):
        config._trigger_discovery(config.manufacturer.pk)


def save_discovery_cidr(cidr, *args, **kwargs) -> None:
    """Save DiscoveryCIDR and trigger discovery scan."""
    from micboard.models.discovery.registry import DiscoveryCIDR as _DiscoveryCIDR

    super(_DiscoveryCIDR, cidr).save(*args, **kwargs)
    cidr._trigger_discovery()


def save_discovery_fqdn(fqdn, *args, **kwargs) -> None:
    """Save DiscoveryFQDN and trigger discovery scan."""
    from micboard.models.discovery.registry import DiscoveryFQDN as _DiscoveryFQDN

    super(_DiscoveryFQDN, fqdn).save(*args, **kwargs)
    fqdn._trigger_discovery()


def delete_discovery_fqdn(fqdn, *args, **kwargs):
    """Delete DiscoveryFQDN and trigger discovery scan."""
    manufacturer_pk = fqdn.manufacturer_id
    from micboard.models.discovery.registry import DiscoveryFQDN as _DiscoveryFQDN

    result = super(_DiscoveryFQDN, fqdn).delete(*args, **kwargs)
    fqdn._trigger_discovery(manufacturer_pk)
    return result
