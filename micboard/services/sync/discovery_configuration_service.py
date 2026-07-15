"""Persist bounded discovery sources and vendor capability snapshots."""

from __future__ import annotations

import ipaddress
import json
import logging
from collections.abc import Iterable
from itertools import islice
from typing import Any

from micboard.discovery.limits import (
    MAX_DISCOVERY_CANDIDATES,
    MAX_DISCOVERY_METADATA_STRING_LENGTH,
)
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveryCIDR, DiscoveryFQDN, MicboardConfig
from micboard.services.common.base.utils import validate_hostname
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

SUPPORTED_MODELS_CONFIG_KEY = "SUPPORTED_DEVICE_MODELS"


class DiscoveryConfigurationService:
    """Validate and persist inputs that configure discovery synchronization."""

    @staticmethod
    def _bound_entries(values: Iterable[str] | None) -> tuple[list[str], bool]:
        """Consume no more than the global discovery input budget."""
        entries = list(islice(iter(values or ()), MAX_DISCOVERY_CANDIDATES + 1))
        return entries[:MAX_DISCOVERY_CANDIDATES], len(entries) <= MAX_DISCOVERY_CANDIDATES

    @staticmethod
    def add_entries(
        manufacturer: Manufacturer,
        *,
        cidrs: Iterable[str] | None,
        fqdns: Iterable[str] | None,
    ) -> bool:
        """Persist requested discovery sources, containing invalid individual entries."""
        bounded_cidrs, cidrs_complete = DiscoveryConfigurationService._bound_entries(cidrs)
        bounded_fqdns, fqdns_complete = DiscoveryConfigurationService._bound_entries(fqdns)
        inputs_complete = cidrs_complete and fqdns_complete
        if not inputs_complete:
            logger.warning("Discovery configuration input exceeded the hard limit")

        for cidr in bounded_cidrs:
            try:
                canonical_cidr = str(ipaddress.ip_network(str(cidr).strip(), strict=False))
            except ValueError:
                logger.warning("Invalid CIDR ignored")
                inputs_complete = False
                continue
            try:
                DiscoveryCIDR.objects.get_or_create(
                    manufacturer=manufacturer,
                    cidr=canonical_cidr,
                )
            except Exception as exc:
                inputs_complete = False
                logger.exception(
                    "Could not persist validated discovery CIDR",
                    exc_info=sanitized_exception_info(exc),
                )

        for fqdn in bounded_fqdns:
            canonical_fqdn = str(fqdn).strip().rstrip(".").lower()
            if not validate_hostname(canonical_fqdn):
                logger.warning("Invalid FQDN ignored")
                inputs_complete = False
                continue
            try:
                DiscoveryFQDN.objects.get_or_create(
                    manufacturer=manufacturer,
                    fqdn=canonical_fqdn,
                )
            except Exception as exc:
                inputs_complete = False
                logger.exception(
                    "Could not persist validated discovery FQDN",
                    exc_info=sanitized_exception_info(exc),
                )
        return inputs_complete

    @staticmethod
    def persist_supported_models(manufacturer: Manufacturer, device_client: Any) -> bool:
        """Persist a vendor-neutral supported-model snapshot when the API exposes one."""
        if device_client is None or not hasattr(device_client, "get_supported_device_models"):
            return True

        try:
            raw_models = device_client.get_supported_device_models() or []
            models = list(islice(iter(raw_models), MAX_DISCOVERY_CANDIDATES + 1))
        except Exception as exc:
            logger.exception(
                "Could not fetch supported device models from API",
                exc_info=sanitized_exception_info(exc),
            )
            return False
        if len(models) > MAX_DISCOVERY_CANDIDATES or any(
            not isinstance(model, str) or len(model) > MAX_DISCOVERY_METADATA_STRING_LENGTH
            for model in models
        ):
            logger.warning("Supported-model payload was invalid or exceeded the hard limit")
            return False
        if not models:
            return True

        try:
            config, created = MicboardConfig.objects.get_or_create(
                key=SUPPORTED_MODELS_CONFIG_KEY,
                manufacturer=manufacturer,
                defaults={"value": json.dumps(models)},
            )
            if not created:
                config.value = json.dumps(models)
                config.save(update_fields=["value"])
            logger.info("Persisted %d supported models for %s", len(models), manufacturer.code)
        except Exception as exc:
            logger.exception(
                "Error persisting supported models for %s",
                manufacturer.code,
                exc_info=sanitized_exception_info(exc),
            )
            return False
        return True
