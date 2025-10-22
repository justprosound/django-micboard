"""Compatibility helper providing discovery helper functions expected by
legacy imports under micboard.manufacturers.shure.discovery_sync.
"""

from __future__ import annotations

from django.core.cache import cache

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import Manufacturer, Receiver


def get_discovery_candidates(
    manufacturer_code: str,
    *,
    scan_cidrs: bool = False,
    scan_fqdns: bool = False,
    max_hosts: int = 1024,
):
    """Return discovery candidates combining remote discovery IPs and local Receivers.

    This implementation intentionally uses the local module-level
    `get_manufacturer_plugin` so tests can monkeypatch it when necessary.
    """
    try:
        manufacturer = Manufacturer.objects.get(code=manufacturer_code)
    except Manufacturer.DoesNotExist:
        return []

    candidates: list[str] = []

    # 1) Remote discovery IPs from manufacturer's configured client (if any)
    try:
        plugin_cls = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_cls(manufacturer)
        client = getattr(plugin, "client", None)
        if client and hasattr(client, "get_discovery_ips"):
            try:
                remote_ips = client.get_discovery_ips() or []
                candidates.extend([ip for ip in remote_ips if isinstance(ip, str)])
            except Exception:
                # ignore remote fetch errors
                pass
    except Exception:
        # If plugin lookup fails, continue with local sources
        pass

    # 2) Local receivers for this manufacturer
    try:
        for rx in Receiver.objects.filter(manufacturer=manufacturer):
            if rx.ip:
                candidates.append(rx.ip)
    except Exception:
        pass

    # Deduplicate preserving order
    seen = set()
    deduped: list[str] = []
    for ip in candidates:
        if ip not in seen:
            seen.add(ip)
            deduped.append(ip)

    return deduped


def compute_discovery_candidates_with_progress(
    manufacturer_code: str,
    status_key: str,
    *,
    scan_cidrs: bool = False,
    scan_fqdns: bool = False,
    max_hosts: int = 1024,
):
    """Compute candidates and set a status key in cache to simulate progress for tests."""
    # Mark running
    cache.set(
        status_key, {"status": "running", "items_total": 0, "items_processed": 0}, timeout=3600
    )
    try:
        candidates = get_discovery_candidates(
            manufacturer_code, scan_cidrs=scan_cidrs, scan_fqdns=scan_fqdns, max_hosts=max_hosts
        )
        cache.set(
            status_key,
            {
                "status": "done",
                "items_total": len(candidates),
                "items_processed": len(candidates),
                "count": len(candidates),
            },
            timeout=3600,
        )
        return candidates
    except Exception:
        cache.set(status_key, {"status": "error", "error": "exception"}, timeout=3600)
        return []
