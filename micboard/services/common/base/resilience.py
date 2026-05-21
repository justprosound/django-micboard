from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .circuit_breaker import CircuitOpenError

logger = logging.getLogger(__name__)


class BasePollingMixin:
    def poll_all_devices(self) -> dict[str, dict[str, Any]]:
        transformer = self._get_transformer()

        try:
            devices = self.get_devices()  # type: ignore[attr-defined]
            logger.info("Polling %d devices from %s API", len(devices), self.__class__.__name__)
        except CircuitOpenError:
            logger.warning("Circuit open for %s; skipping device polling", self.__class__.__name__)
            return {}
        except Exception:
            logger.exception("Failed to get device list")
            return {}

        data: dict[str, dict[str, Any]] = {}
        for device in devices:
            device_id = device.get("id")
            if not device_id:
                logger.warning("Device missing 'id' field: %s", device)
                continue

            device_data = self._poll_single_device(device_id, transformer)
            if device_data:
                data[device_id] = device_data

        self._log_firmware_coverage(data)
        logger.info("Successfully polled %d devices", len(data))
        return data

    def _poll_single_device(self, device_id: str, transformer: Any) -> dict[str, Any] | None:
        try:
            device_data = self.get_device(device_id)  # type: ignore[attr-defined]
            if not device_data:
                logger.warning("No data returned for device %s", device_id)
                return None

            try:
                device_data = self._enrich_device_data(device_id, device_data)  # type: ignore[attr-defined]
            except Exception:
                logger.debug("Enrichment failed for device %s", device_id)

            channels = self.get_device_channels(device_id)  # type: ignore[attr-defined]
            device_data["channels"] = channels

            transformed = transformer.transform_device_data(device_data)
            if transformed:
                return transformed
            else:
                logger.warning("Failed to transform data for device %s", device_id)
                return None
        except CircuitOpenError:
            logger.warning(
                "Circuit open for %s while polling device %s; skipping",
                self.__class__.__name__,
                device_id,
            )
            return None
        except Exception:
            logger.exception("Error polling device %s", device_id)
            return None

    def _log_firmware_coverage(self, data: dict[str, dict[str, Any]]) -> None:
        missing_fw = [d for d in data.values() if not d.get("firmware")]
        if missing_fw:
            logger.warning("%d devices missing firmware info", len(missing_fw))
        else:
            logger.info("Firmware info present for all devices")

    @abstractmethod
    def _get_transformer(self) -> Any:
        raise NotImplementedError()


def create_resilient_session(
    *,
    max_retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: list[int] | None = None,
    pool_connections: int = 10,
    pool_maxsize: int = 20,
) -> requests.Session:
    session = requests.Session()
    status_forcelist = status_forcelist or [429, 500, 502, 503, 504]
    retry = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry, pool_connections=pool_connections, pool_maxsize=pool_maxsize
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
