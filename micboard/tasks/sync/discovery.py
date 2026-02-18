"""Discovery-related background tasks for the micboard app."""

# Discovery-related background tasks for the micboard app.
from __future__ import annotations

import json
import logging
import re
import socket
from typing import Any

from django.core.cache import cache
from django.utils import timezone

from micboard.integrations.common.utils import validate_hostname
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import (
    DiscoveryCIDR,
    DiscoveryFQDN,
    DiscoveryJob,
    MicboardConfig,
)
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.sync.discovery_service import DiscoveryService

logger = logging.getLogger(__name__)


def _resolve_validated_fqdn(ip: str) -> str | None:
    """Resolve PTR and validate forward lookup matches the IP."""
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
    except Exception:
        return None

    if not hostname:
        return None

    fqdn = hostname.rstrip(".")
    if not validate_hostname(fqdn):
        return None

    try:
        infos = socket.getaddrinfo(fqdn, None)
        ips = {info[4][0] for info in infos}
    except Exception:
        return None

    return fqdn if ip in ips else None


def _humanize_fqdn(fqdn: str) -> str:
    """Convert an FQDN into a human-friendly device name."""
    label = fqdn.split(".")[0]
    label = re.sub(r"[_-]+", " ", label)
    label = re.sub(r"(wm)(\d*)$", r" WM\2", label, flags=re.IGNORECASE)
    label = re.sub(r"([a-zA-Z])([0-9])", r"\1 \2", label)
    label = re.sub(r"\s+", " ", label).strip()
    words = []
    for word in label.split(" "):
        if word.lower() == "wm":
            words.append("WM")
        else:
            words.append(word.capitalize())
    return " ".join(words)


def sync_receiver_discovery(chassis_id: int):
    """Task to ensure a wireless chassis is known to the manufacturer's discovery list."""
    try:
        chassis = WirelessChassis.objects.get(pk=chassis_id)
        discovery_service = DiscoveryService()
        if chassis.ip:
            discovery_service.add_discovery_candidate(
                chassis.ip, chassis.manufacturer, source="chassis_save"
            )
    except WirelessChassis.DoesNotExist:
        logger.warning("WirelessChassis with ID %s not found for discovery sync.", chassis_id)
    except Exception:
        logger.exception("Error in sync_receiver_discovery task for chassis ID %s", chassis_id)


def run_manufacturer_discovery_task(manufacturer_id: int, scan_cidrs: bool, scan_fqdns: bool):
    """Task to run discovery for a specific manufacturer."""
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
        discovery_service = DiscoveryService()
        discovery_service._run_manufacturer_discovery(
            manufacturer, scan_cidrs=scan_cidrs, scan_fqdns=scan_fqdns, max_hosts=1024
        )
        logger.info(
            "Discovery scan triggered for %s (CIDRs: %s, FQDNs: %s)",
            manufacturer.code,
            scan_cidrs,
            scan_fqdns,
        )
    except Manufacturer.DoesNotExist:
        logger.warning("Manufacturer with ID %s not found for discovery task.", manufacturer_id)
    except Exception:
        logger.exception("Error running discovery scan for manufacturer ID %s", manufacturer_id)


def cache_all_discovery_candidates(scan_cidrs: bool = False, scan_fqdns: bool = False):
    """Task to compute and cache discovery candidate IPs for all manufacturers."""
    logger.info(
        "Starting task to cache all discovery candidates (CIDRs: %s, FQDNs: %s)",
        scan_cidrs,
        scan_fqdns,
    )
    for m in Manufacturer.objects.all():
        try:
            run_manufacturer_discovery_task(m.pk, scan_cidrs, scan_fqdns)
            # After running discovery, retrieve the updated candidates from the client
            discovery_service = DiscoveryService()
            client = discovery_service._get_manufacturer_client(m)
            ips = client.get_discovery_ips()
            cache_key = f"discovery_candidates_{m.code}_{int(scan_cidrs)}_{int(scan_fqdns)}"
            cache.set(cache_key, {m.code: {"ips": ips}}, timeout=300)
            logger.info("Cached %d candidates for %s", len(ips), m.code)
        except Exception:
            logger.exception("Failed to compute discovery candidates for %s", m.code)


def run_discovery_sync_task(
    manufacturer_id: int,
    add_cidrs: list[str] | None = None,
    add_fqdns: list[str] | None = None,
    scan_cidrs: bool = False,
    scan_fqdns: bool = False,
    max_hosts: int = 1024,
):
    """Task to run a discovery synchronization for the given manufacturer."""
    summary: dict[str, Any] = {
        "manufacturer": manufacturer_id,
        "status": "running",
        "created_receivers": 0,
        "missing_ips_submitted": 0,
        "scanned_ips_submitted": 0,
        "errors": [],
    }

    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
    except Manufacturer.DoesNotExist:
        msg = f"Manufacturer {manufacturer_id} not found"
        logger.error(msg)
        summary["status"] = "failed"
        summary["errors"].append(msg)
        return summary

    job = DiscoveryJob.objects.create(
        manufacturer=manufacturer,
        action="sync",
        status="running",
        started_at=timezone.now(),
    )

    try:
        discovery_service = DiscoveryService()

        # Optionally add CIDR and FQDN entries to config
        _add_config_entries(manufacturer, add_cidrs, add_fqdns)

        # Initialize plugin and client
        plugin, client = _initialize_plugin_client(manufacturer, summary)
        if not plugin or not client:
            return summary

        # 0. Fetch and persist supported device models for this manufacturer
        _persist_supported_models(manufacturer, client)

        # 1) Poll API for devices and create/update receivers
        api_devices = _poll_and_create_receivers(manufacturer, plugin, summary)
        if api_devices is None:
            return summary

        discovered_ips = {
            ip for d in api_devices or [] if (ip := d.get("ip") or d.get("ipAddress")) is not None
        }

        # Read CIDR/FQDN config
        cidrs = [dc.cidr for dc in DiscoveryCIDR.objects.filter(manufacturer=manufacturer)]
        fqdns = [df.fqdn for df in DiscoveryFQDN.objects.filter(manufacturer=manufacturer)]

        # 2) Submit missing local receiver IPs to discovery
        _submit_missing_ips(manufacturer, discovered_ips, discovery_service, summary)

        # 3) Optionally expand CIDRs and resolve FQDNs and submit candidates
        _submit_scanned_candidates(
            manufacturer,
            cidrs,
            fqdns,
            discovered_ips,
            scan_cidrs,
            scan_fqdns,
            max_hosts,
            discovery_service,
            summary,
        )

        # Finalize job
        _finalize_job(job, summary)

        # Broadcast updated device list to frontend via signals for consistency
        _broadcast_results(manufacturer)

        return summary

    except Exception as exc:
        logger.exception("Error in discovery sync task: %s", exc)
        job.status = "failed"
        job.note = str(exc)
        job.finished_at = timezone.now()
        job.save()
        summary["status"] = "failed"
        summary["errors"].append(str(exc))
        return summary


def _add_config_entries(
    manufacturer: Manufacturer, add_cidrs: list[str] | None, add_fqdns: list[str] | None
) -> None:
    """Add CIDR and FQDN entries to config."""
    if add_cidrs:
        for c in add_cidrs:
            try:
                DiscoveryCIDR.objects.get_or_create(manufacturer=manufacturer, cidr=c)
            except Exception:
                logger.warning("Invalid CIDR ignored: %s", c)

    if add_fqdns:
        for f in add_fqdns:
            if f:
                DiscoveryFQDN.objects.get_or_create(manufacturer=manufacturer, fqdn=f)


def _initialize_plugin_client(
    manufacturer: Manufacturer, summary: dict[str, Any]
) -> tuple[Any, Any] | tuple[None, None]:
    """Initialize plugin and client, return (plugin, client) or (None, None) on failure."""
    try:
        from micboard.manufacturers import get_manufacturer_plugin

        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)
        client = plugin.get_client()
        return plugin, client
    except Exception as exc:
        logger.exception("Failed to initialize plugin: %s", exc)
        summary["status"] = "failed"
        summary["errors"].append(str(exc))
        return None, None


def _persist_supported_models(manufacturer: Manufacturer, client: Any) -> None:
    """Fetch and persist supported device models."""
    try:
        models = []
        try:
            if hasattr(client, "get_supported_device_models"):
                models = client.get_supported_device_models()
        except Exception:
            logger.debug("Could not fetch supported device models from API")

        if models:
            # Ensure models is a list of strings, not a MagicMock
            if not isinstance(models, list):
                models = list(models)

            key = "SHURE_SUPPORTED_MODELS"
            cfg_obj, created = MicboardConfig.objects.get_or_create(
                key=key,
                manufacturer=manufacturer,
                defaults={"value": json.dumps(models)},
            )
            if not created:
                cfg_obj.value = json.dumps(models)
                cfg_obj.save()
            logger.info("Persisted %d supported models for %s", len(models), manufacturer.code)
    except Exception as exc:
        logger.exception("Error persisting supported device models: %s", exc)


def _poll_and_create_receivers(
    manufacturer: Manufacturer, plugin: Any, summary: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Poll API for devices and create/update DiscoveryQueue entries."""
    from micboard.models import DiscoveryQueue

    api_devices: list[dict[str, Any]] = []
    try:
        api_devices = plugin.get_devices() or []
        if not api_devices:
            logger.info("No devices returned from API")
        else:
            for dev in api_devices:
                device_id = dev.get("id") or dev.get("api_device_id") or dev.get("deviceId")
                serial = dev.get("serial") or dev.get("serialNumber")
                ip = dev.get("ip") or dev.get("ipAddress") or dev.get("ipv4")
                name = dev.get("name") or dev.get("model") or ""
                model = dev.get("model") or dev.get("deviceType") or ""

                fqdn = _resolve_validated_fqdn(ip) if ip else None
                if fqdn:
                    dev.setdefault("fqdn", fqdn)
                    dev.setdefault("ptr_validated", True)
                    if not name or name == model or name == ip:
                        name = _humanize_fqdn(fqdn)

                if not serial or not ip:
                    logger.warning("Skipping device with missing serial/ip: %s", dev)
                    continue

                # Determine device type
                device_type = dev.get("type", "UNKNOWN")
                if "SBC" in model.upper() or "charger" in device_type.lower():
                    device_type = "charger"
                elif "transmitter" in device_type.lower():
                    device_type = "transmitter"
                elif "transceiver" in device_type.lower():
                    device_type = "transceiver"
                else:
                    device_type = "receiver"

                # Create/Update DiscoveryQueue entry
                q_entry, created = DiscoveryQueue.objects.update_or_create(
                    manufacturer=manufacturer,
                    serial_number=serial,
                    defaults={
                        "api_device_id": device_id or "",
                        "ip": ip,
                        "name": name,
                        "fqdn": fqdn or "",
                        "model": model,
                        "device_type": device_type,
                        "firmware_version": dev.get("firmware")
                        or dev.get("firmware_version")
                        or dev.get("firmwareVersion", ""),
                        "metadata": dev,
                        "status": "pending",
                    },
                )

                # Auto-check for duplicates/movements
                conflicts = q_entry.check_for_duplicates()
                q_entry.is_duplicate = conflicts["is_duplicate"]
                q_entry.is_ip_conflict = conflicts["is_ip_conflict"]
                q_entry.existing_device = conflicts["existing_device"]
                q_entry.existing_charger = conflicts["existing_charger"]
                q_entry.save()

                if created:
                    summary["created_receivers"] += 1
        return api_devices
    except Exception as exc:
        logger.exception("Error polling API: %s", exc)
        summary["status"] = "failed"
        summary["errors"].append(str(exc))
        return None


def _submit_missing_ips(
    manufacturer: Manufacturer,
    discovered_ips: set[str],
    discovery_service: DiscoveryService,
    summary: dict[str, Any],
) -> None:
    """Submit missing local chassis and discovered device IPs to discovery."""
    missing_ips = []

    # Check WirelessChassis objects (configured devices)
    for chassis in WirelessChassis.objects.filter(manufacturer=manufacturer):
        if not chassis.ip:
            continue
        if chassis.ip not in discovered_ips:
            missing_ips.append(chassis.ip)

    # Also check DiscoveredDevice objects (devices found but not yet configured)
    from micboard.models import DiscoveredDevice

    for dev in DiscoveredDevice.objects.filter(manufacturer=manufacturer):
        if dev.ip and dev.ip not in discovered_ips and dev.ip not in missing_ips:
            missing_ips.append(dev.ip)

    if missing_ips:
        for ip in missing_ips:
            if discovery_service.add_discovery_candidate(
                ip, manufacturer, source="missing_chassis"
            ):
                summary["missing_ips_submitted"] += 1
            else:
                summary["errors"].append(f"Failed to submit missing IP {ip}")


def _submit_scanned_candidates(
    manufacturer: Manufacturer,
    cidrs: list[str],
    fqdns: list[str],
    discovered_ips: set[str],
    scan_cidrs: bool,
    scan_fqdns: bool,
    max_hosts: int,
    discovery_service: DiscoveryService,
    summary: dict[str, Any],
) -> None:
    """Expand CIDRs and resolve FQDNs and submit candidates."""
    ips_to_submit: list[str] = []
    if scan_cidrs and cidrs:
        from micboard.discovery.network_utils import expand_cidrs

        for cidr in cidrs:
            for ip in expand_cidrs([cidr], max_hosts=max_hosts):
                if ip not in discovered_ips:
                    ips_to_submit.append(ip)

    if scan_fqdns and fqdns:
        from micboard.discovery.network_utils import resolve_fqdns

        resolved = resolve_fqdns(fqdns)
        for _f, ips in resolved.items():
            for ip in ips:
                if ip not in discovered_ips:
                    ips_to_submit.append(ip)

    ips_to_submit = list(dict.fromkeys(ips_to_submit))
    if ips_to_submit:
        for ip in ips_to_submit:
            if discovery_service.add_discovery_candidate(
                ip, manufacturer, source="scanned_candidate"
            ):
                summary["scanned_ips_submitted"] += 1
            else:
                summary["errors"].append(f"Failed to submit scanned IP {ip}")


def _finalize_job(job: DiscoveryJob, summary: dict[str, Any]) -> None:
    """Finalize the discovery job with status and metrics."""
    job.status = "success" if not summary["errors"] else "failed"
    job.finished_at = timezone.now()
    job.items_scanned = summary.get("scanned_ips_submitted", 0) + summary.get(
        "missing_ips_submitted", 0
    )
    job.items_submitted = job.items_scanned
    if summary["errors"]:
        job.note = "; ".join(summary["errors"])[:1024]
    job.save()
    summary["status"] = job.status


def _broadcast_results(manufacturer: Manufacturer) -> None:
    """Broadcast updated device list via BroadcastService."""
    try:
        from micboard.services.notification.broadcast_service import BroadcastService

        chassis_qs = WirelessChassis.objects.filter(manufacturer=manufacturer)
        serialized_data = {
            "receivers": [
                {
                    "id": chassis.id,
                    "api_device_id": chassis.api_device_id,
                    "name": chassis.name,
                    "ip": str(chassis.ip) if chassis.ip else None,
                    "status": chassis.status,
                    "model": chassis.model,
                }
                for chassis in chassis_qs
            ]
        }
        BroadcastService.broadcast_device_update(manufacturer=manufacturer, data=serialized_data)
    except Exception:
        logger.debug("Failed to broadcast results from discovery_sync")
