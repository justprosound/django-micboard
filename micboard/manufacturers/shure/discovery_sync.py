"""Compatibility shim providing discovery helper functions for the Shure
manufacturer package path. Tests and older code import
`micboard.manufacturers.shure.discovery_sync` — provide the expected
functions by delegating to micboard.discovery.service.DiscoveryService.
"""

from __future__ import annotations

from micboard.manufacturers import get_manufacturer_plugin as _get_manufacturer_plugin
from micboard.services.discovery_service_new import DiscoveryService


def get_discovery_candidates(
    manufacturer_code: str,
    *,
    scan_cidrs: bool = False,
    scan_fqdns: bool = False,
    max_hosts: int = 1024,
):
    svc = DiscoveryService()
    return svc.get_discovery_candidates(
        manufacturer_code, scan_cidrs=scan_cidrs, scan_fqdns=scan_fqdns, max_hosts=max_hosts
    )


def compute_discovery_candidates_with_progress(
    manufacturer_code: str,
    status_key: str,
    *,
    scan_cidrs: bool = False,
    scan_fqdns: bool = False,
    max_hosts: int = 1024,
):
    svc = DiscoveryService()
    return svc.compute_discovery_candidates_with_progress(
        manufacturer_code,
        status_key,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
        max_hosts=max_hosts,
    )


# Expose a loader for tests that patch this symbol; delegate to the centralized
# manufacturers loader by default.
def get_manufacturer_plugin(code: str):
    return _get_manufacturer_plugin(code)
