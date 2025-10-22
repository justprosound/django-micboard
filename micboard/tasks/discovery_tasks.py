"""
Discovery-related background tasks for the micboard app.
"""

# Discovery-related background tasks for the micboard app.
from __future__ import annotations

import json
import logging

from django.core.cache import cache
from django.utils import timezone

from micboard.discovery.service import DiscoveryService
from micboard.models import (
    DiscoveryCIDR,
    DiscoveryFQDN,
    DiscoveryJob,
    Manufacturer,
    MicboardConfig,
    Receiver,
)

logger = logging.getLogger(__name__)


def sync_receiver_discovery(receiver_id: int):
    """
    Task to ensure a receiver is known to the manufacturer's discovery list.
    """
    try:
        receiver = Receiver.objects.get(pk=receiver_id)
        discovery_service = DiscoveryService()
        if receiver.ip:
            discovery_service.add_discovery_candidate(
                receiver.ip, receiver.manufacturer, source="receiver_save"
            )
    except Receiver.DoesNotExist:
        logger.warning("Receiver with ID %s not found for discovery sync.", receiver_id)
    except Exception:
        logger.exception("Error in sync_receiver_discovery task for receiver ID %s", receiver_id)


def run_manufacturer_discovery_task(manufacturer_id: int, scan_cidrs: bool, scan_fqdns: bool):
    """
    Task to run discovery for a specific manufacturer.
    """
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
        discovery_service = DiscoveryService()
        discovery_service._run_manufacturer_discovery(
            manufacturer, scan_cidrs=scan_cidrs, scan_fqdns=scan_fqdns
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
    """
    Task to compute and cache discovery candidate IPs for all manufacturers.
    """
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
    """
    Task to run a discovery synchronization for the given manufacturer.
    """
    summary = {
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
        manufacturer=manufacturer, action="sync", status="running", started_at=timezone.now()
    )

    # Optionally add CIDR and FQDN entries to config
    if add_cidrs:
        for c in add_cidrs:
            try:
                # ipaddress.ip_network(c) # Validation should happen before enqueuing task
                DiscoveryCIDR.objects.get_or_create(manufacturer=manufacturer, cidr=c)
            except Exception:
                logger.warning("Invalid CIDR ignored: %s", c)

    if add_fqdns:
        for f in add_fqdns:
            if f:
                DiscoveryFQDN.objects.get_or_create(manufacturer=manufacturer, fqdn=f)

    # Initialize plugin and client
    try:
        from micboard.manufacturers import get_manufacturer_plugin

        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)
        client = plugin.get_client()
    except Exception as exc:
        logger.exception("Failed to initialize plugin: %s", exc)
        job.status = "failed"
        job.note = str(exc)
        job.finished_at = timezone.now()
        job.save()
        summary["status"] = "failed"
        summary["errors"].append(str(exc))
        return summary

    discovery_service = DiscoveryService()

    # 0. Fetch and persist supported device models for this manufacturer
    try:
        models = []
        try:
            # Assuming client has get_supported_device_models method
            if hasattr(client, "get_supported_device_models"):
                models = client.get_supported_device_models()
        except Exception:
            logger.debug("Could not fetch supported device models from API")

        if models:
            key = "SHURE_SUPPORTED_MODELS"
            cfg_obj, created = MicboardConfig.objects.get_or_create(
                key=key, manufacturer=manufacturer, defaults={"value": json.dumps(models)}
            )
            if not created:
                # Overwrite with latest list
                cfg_obj.value = json.dumps(models)
                cfg_obj.save()
            logger.info("Persisted %d supported models for %s", len(models), manufacturer.code)

    except Exception as exc:
        logger.exception("Error persisting supported device models: %s", exc)

    # 1) Poll API for devices and create/update receivers
    api_devices = []
    try:
        api_devices = plugin.get_devices() or []
        if not api_devices:
            logger.info("No devices returned from API")
        else:
            for dev in api_devices:
                device_id = dev.get("id") or dev.get("api_device_id")
                ip = dev.get("ip") or dev.get("ipAddress") or dev.get("ipv4")
                name = dev.get("name") or dev.get("model") or ""

                if not device_id or not ip:
                    logger.warning("Skipping device with missing id/ip: %s", dev)
                    continue

                rx, created = Receiver.objects.update_or_create(
                    api_device_id=device_id,
                    manufacturer=manufacturer,
                    defaults={"ip": ip, "name": name, "is_active": True},
                )
                if created:
                    summary["created_receivers"] += 1
    except Exception as exc:
        logger.exception("Error polling API: %s", exc)
        job.status = "failed"
        job.note = str(exc)
        job.finished_at = timezone.now()
        job.save()
        summary["status"] = "failed"
        summary["errors"].append(str(exc))
        return summary

    discovered_ips = {d.get("ip") or d.get("ipAddress") for d in api_devices or []}

    # Read CIDR/FQDN config
    cidrs = [dc.cidr for dc in DiscoveryCIDR.objects.filter(manufacturer=manufacturer)]
    fqdns = [df.fqdn for df in DiscoveryFQDN.objects.filter(manufacturer=manufacturer)]

    # 2) Submit missing local receiver IPs to discovery
    missing_ips = []
    for rx in Receiver.objects.filter(manufacturer=manufacturer):
        if not rx.ip:
            continue
        if rx.ip not in discovered_ips:
            missing_ips.append(rx.ip)

    if missing_ips:
        for ip in missing_ips:
            if discovery_service.add_discovery_candidate(
                ip, manufacturer, source="missing_receiver"
            ):
                summary["missing_ips_submitted"] += 1
            else:
                summary["errors"].append(f"Failed to submit missing IP {ip}")

    # 3) Optionally expand CIDRs and resolve FQDNs and submit candidates
    ips_to_submit: list[str] = []
    if scan_cidrs and cidrs:
        from micboard.discovery.legacy import expand_cidrs

        for cidr in cidrs:
            for ip in expand_cidrs([cidr], max_hosts=max_hosts):
                if ip not in discovered_ips:
                    ips_to_submit.append(ip)

    if scan_fqdns and fqdns:
        from micboard.discovery.legacy import resolve_fqdns

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

    job.status = "success" if not summary["errors"] else "failed"
    job.finished_at = timezone.now()
    job.items_scanned = len(ips_to_submit)
    job.items_submitted = summary.get("scanned_ips_submitted", 0) + summary.get(
        "missing_ips_submitted", 0
    )
    if summary["errors"]:
        job.note = "; ".join(summary["errors"])[:1024]
    job.save()

    summary["status"] = job.status
    # Broadcast updated device list to frontend via signals for consistency
    try:
        from micboard.serializers import ReceiverSummarySerializer
        from micboard.signals.broadcast_signals import devices_polled

        # data = {"receivers": serialize_receivers(include_extra=False)}
        # devices_polled.send(run_discovery_sync, manufacturer=manufacturer, data=data)
        # Re-serialize all receivers for the manufacturer and broadcast
        serialized_data = {
            "receivers": ReceiverSummarySerializer(
                Receiver.objects.filter(manufacturer=manufacturer), many=True
            ).data
        }
        devices_polled.send(sender=None, manufacturer=manufacturer, data=serialized_data)

    except Exception:
        logger.debug("Failed to emit devices_polled signal from discovery_sync")
    return summary
