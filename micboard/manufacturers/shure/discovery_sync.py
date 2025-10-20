"""
Shared discovery sync helper for Shure plugin.

This module exposes run_discovery_sync which implements the logic from the
management command so it can be invoked from signals or the command.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from typing import Any, cast

from django.utils import timezone

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import DiscoveryJob, Manufacturer, MicboardConfig, Receiver

logger = logging.getLogger(__name__)


def run_discovery_sync(
    manufacturer_code: str,
    *,
    add_cidrs: list[str] | None = None,
    add_fqdns: list[str] | None = None,
    scan_cidrs: bool = False,
    scan_fqdns: bool = False,
    max_hosts: int = 1024,
) -> dict[str, Any]:
    """Run a discovery synchronization for the given manufacturer.

    Returns a summary dict with status and counts. This function does not
    raise for recoverable errors; errors are captured in the returned summary
    and logged to assist callers like signals.
    """
    summary: dict[str, Any] = {
        "manufacturer": manufacturer_code,
        "status": "running",
        "created_receivers": 0,
        "missing_ips_submitted": 0,
        "scanned_ips_submitted": 0,
        "errors": [],
    }

    try:
        manufacturer = Manufacturer.objects.get(code=manufacturer_code)
    except Manufacturer.DoesNotExist:
        msg = f"Manufacturer {manufacturer_code} not found"
        logger.error(msg)
        summary["status"] = "failed"
        summary["errors"].append(msg)
        return summary

    job = DiscoveryJob.objects.create(
        manufacturer=manufacturer, action="sync", status="running", started_at=timezone.now()
    )

    # Optionally add CIDR and FQDN entries to config
    if add_cidrs:
        valid = []
        for c in add_cidrs:
            try:
                ipaddress.ip_network(c)
                valid.append(c)
            except Exception:
                logger.warning("Invalid CIDR ignored: %s", c)
        if valid:
            key = "SHURE_DISCOVERY_CIDRS"
            cfg_obj, created = MicboardConfig.objects.get_or_create(
                key=key, manufacturer=manufacturer, defaults={"value": json.dumps(valid)}
            )
            if not created:
                existing = json.loads(cfg_obj.value or "[]")
                merged = list(dict.fromkeys(existing + valid))
                cfg_obj.value = json.dumps(merged)
                cfg_obj.save()

    if add_fqdns:
        fqdns = [f for f in add_fqdns if f]
        if fqdns:
            key = "SHURE_DISCOVERY_FQDNS"
            cfg_obj, created = MicboardConfig.objects.get_or_create(
                key=key, manufacturer=manufacturer, defaults={"value": json.dumps(fqdns)}
            )
            if not created:
                existing = json.loads(cfg_obj.value or "[]")
                merged = list(dict.fromkeys(existing + fqdns))
                cfg_obj.value = json.dumps(merged)
                cfg_obj.save()

    # Initialize plugin and client
    try:
        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)
        # plugin may implement additional attributes (like .client) not present on the
        # abstract base class; cast to Any to appease static type checkers
        client = cast(Any, plugin).client
    except Exception as exc:
        logger.exception("Failed to initialize plugin: %s", exc)
        job.status = "failed"
        job.note = str(exc)
        job.finished_at = timezone.now()
        job.save()
        summary["status"] = "failed"
        summary["errors"].append(str(exc))
        return summary

    # 0. Fetch and persist supported device models for this manufacturer
    try:
        models = []
        try:
            models = client.get_supported_device_models()
        except Exception:
            logger.debug("Could not fetch supported device models from Shure API")

        if models:
            key = "SHURE_SUPPORTED_MODELS"
            cfg_obj, created = MicboardConfig.objects.get_or_create(
                key=key, manufacturer=manufacturer, defaults={"value": json.dumps(models)}
            )
            if not created:
                # Overwrite with latest list
                cfg_obj.value = json.dumps(models)
                cfg_obj.save()
            logger.info(
                "Persisted %d supported Shure models for %s", len(models), manufacturer.code
            )
    except Exception as exc:
        logger.exception("Error persisting supported device models: %s", exc)

    # 1) Poll API for devices and create/update receivers
    api_devices = []
    try:
        api_devices = plugin.get_devices() or []
        if not api_devices:
            logger.info("No devices returned from Shure API")
        else:
            for dev in api_devices:
                device_id = dev.get("id") or dev.get("DeviceId")
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
        logger.exception("Error polling Shure API: %s", exc)
        job.status = "failed"
        job.note = str(exc)
        job.finished_at = timezone.now()
        job.save()
        summary["status"] = "failed"
        summary["errors"].append(str(exc))
        return summary

    discovered_ips = {d.get("ip") or d.get("ipAddress") for d in api_devices or []}

    # Read CIDR/FQDN config (for informational use)
    try:
        cidr_cfg = MicboardConfig.objects.get(
            key="SHURE_DISCOVERY_CIDRS", manufacturer=manufacturer
        )
        cidrs = json.loads(cidr_cfg.value or "[]")
    except MicboardConfig.DoesNotExist:
        cidrs = []

    try:
        fqdn_cfg = MicboardConfig.objects.get(
            key="SHURE_DISCOVERY_FQDNS", manufacturer=manufacturer
        )
        fqdns = json.loads(fqdn_cfg.value or "[]")
    except MicboardConfig.DoesNotExist:
        fqdns = []

    # 2) Submit missing local receiver IPs to Shure discovery
    missing_ips = []
    for rx in Receiver.objects.filter(manufacturer=manufacturer):
        if not rx.ip:
            continue
        if rx.ip not in discovered_ips:
            missing_ips.append(rx.ip)

    if missing_ips:
        try:
            ok = client.add_discovery_ips(missing_ips)
            if ok:
                summary["missing_ips_submitted"] = len(missing_ips)
            else:
                msg = "Failed to submit missing IPs to Shure discovery"
                logger.error(msg)
                summary["errors"].append(msg)
        except Exception as exc:
            logger.exception("Failed to submit missing IPs: %s", exc)
            summary["errors"].append(str(exc))

    # 3) Optionally expand CIDRs and resolve FQDNs and submit candidates
    ips_to_submit: list[str] = []
    if scan_cidrs and cidrs:
        from micboard.discovery import expand_cidrs

        for cidr in cidrs:
            for ip in expand_cidrs([cidr], max_hosts=max_hosts):
                if ip not in discovered_ips:
                    ips_to_submit.append(ip)

    if scan_fqdns and fqdns:
        from micboard.discovery import resolve_fqdns

        resolved = resolve_fqdns(fqdns)
        for _f, ips in resolved.items():
            for ip in ips:
                if ip not in discovered_ips:
                    ips_to_submit.append(ip)

    ips_to_submit = list(dict.fromkeys(ips_to_submit))
    if ips_to_submit:
        try:
            ok = client.add_discovery_ips(ips_to_submit)
            if ok:
                summary["scanned_ips_submitted"] = len(ips_to_submit)
            else:
                msg = "Failed to submit scanned IPs to Shure discovery"
                logger.error(msg)
                summary["errors"].append(msg)
        except Exception as exc:
            logger.exception("Error submitting scanned IPs: %s", exc)
            summary["errors"].append(str(exc))

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
        from micboard.serializers import serialize_receivers
        from micboard.signals import devices_polled

        data = {"receivers": serialize_receivers(include_extra=False)}
        devices_polled.send(run_discovery_sync, manufacturer=manufacturer, data=data)
    except Exception:
        logger.debug("Failed to emit devices_polled signal from discovery_sync")
    return summary
