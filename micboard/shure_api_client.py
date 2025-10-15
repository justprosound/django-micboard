from __future__ import annotations

import json
import logging
import time
from functools import wraps
from typing import Any

import requests
import websockets
from django.conf import settings
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class ShureAPIError(Exception):
    """Base exception for Shure System API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: requests.Response | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response

    def __str__(self):
        if self.status_code:
            return f"ShureAPIError: {self.message} (Status: {self.status_code})"
        return f"ShureAPIError: {self.message}"


class ShureAPIRateLimitError(ShureAPIError):
    """Exception for Shure System API rate limit errors (HTTP 429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
        response: requests.Response | None = None,
    ):
        super().__init__(message, status_code=429, response=response)
        self.retry_after = retry_after
        if response and "Retry-After" in response.headers:
            try:
                self.retry_after = int(response.headers["Retry-After"])
            except ValueError:
                pass

    def __str__(self):
        if self.retry_after:
            return (
                f"ShureAPIRateLimitError: {self.message}. Retry after {self.retry_after} seconds."
            )
        return f"ShureAPIRateLimitError: {self.message}"


def rate_limit(calls_per_second: float = 10.0):
    """
    Decorator to rate limit method calls.
    Uses token bucket algorithm with Django cache.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            cache_key = f"rate_limit_{self.__class__.__name__}_{func.__name__}"
            min_interval = 1.0 / calls_per_second

            last_call = cache.get(cache_key, 0)
            now = time.time()
            time_since_last = now - last_call

            if time_since_last < min_interval:
                sleep_time = min_interval - time_since_last
                logger.debug("Rate limiting %s: sleeping %.3fs", func.__name__, sleep_time)
                time.sleep(sleep_time)
                now = time.time()

            cache.set(cache_key, now, timeout=60)
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


class ShureSystemAPIClient:
    """Client for interacting with Shure System API"""

    def __init__(self):
        config = getattr(settings, "MICBOARD_CONFIG", {})
        self.base_url = config.get("SHURE_API_BASE_URL", "http://localhost:8080").rstrip("/")
        self.username = config.get("SHURE_API_USERNAME")
        self.password = config.get("SHURE_API_PASSWORD")
        self.timeout = config.get("SHURE_API_TIMEOUT", 10)
        self.verify_ssl = config.get("SHURE_API_VERIFY_SSL", True)

        # Retry configuration
        self.max_retries = config.get("SHURE_API_MAX_RETRIES", 3)
        self.retry_backoff = config.get("SHURE_API_RETRY_BACKOFF", 0.5)  # seconds
        self.retry_status_codes = config.get(
            "SHURE_API_RETRY_STATUS_CODES", [429, 500, 502, 503, 504]
        )

        # Connection health tracking
        self._last_successful_request = None
        self._consecutive_failures = 0
        self._is_healthy = True

        # Create session with retry strategy and connection pooling
        self.session = requests.Session()

        # Connection pooling configuration
        adapter = HTTPAdapter(
            max_retries=self._create_retry_strategy(),
            pool_connections=10,  # Number of connection pools to cache
            pool_maxsize=20,  # Max connections per pool
            pool_block=False,  # Don't block if pool is full
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if self.username and self.password:
            self.session.auth = (self.username, self.password)

        self.websocket_url = config.get("SHURE_API_WEBSOCKET_URL")
        if not self.websocket_url:
            # Infer from base_url if not explicitly set
            ws_scheme = "wss" if self.base_url.startswith("https") else "ws"
            self.websocket_url = f"{ws_scheme}://{self.base_url.split('://', 1)[1]}/api/v1/subscriptions/websocket/create"

    def _create_retry_strategy(self) -> Retry:
        """Create retry strategy for HTTP requests"""
        return Retry(
            total=self.max_retries,
            backoff_factor=self.retry_backoff,
            status_forcelist=self.retry_status_codes,
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
            raise_on_status=False,  # Let us handle status errors
        )

    def is_healthy(self) -> bool:
        """Check if API client is healthy based on recent requests"""
        return self._is_healthy and self._consecutive_failures < 5

    def check_health(self) -> dict[str, Any]:
        """Perform health check against API and return status"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/health",
                timeout=5,
                verify=self.verify_ssl,
            )
            is_up = response.status_code == 200
            return {
                "status": "healthy" if is_up else "unhealthy",
                "base_url": self.base_url,
                "status_code": response.status_code,
                "consecutive_failures": self._consecutive_failures,
                "last_successful_request": self._last_successful_request,
            }
        except requests.RequestException as e:
            return {
                "status": "unreachable",
                "base_url": self.base_url,
                "error": str(e),
                "consecutive_failures": self._consecutive_failures,
                "last_successful_request": self._last_successful_request,
            }

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Any | None:
        """Make HTTP request with error handling and comprehensive logging"""
        url = f"{self.base_url}{endpoint}"
        logger.debug("Making %s request to %s", method, url)
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify_ssl)

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            result = response.json() if response.content else None

            # Update health tracking on success
            self._last_successful_request = time.time()
            self._consecutive_failures = 0
            self._is_healthy = True

            logger.debug("Request successful: %s %s", method, url)
            return result
        except requests.exceptions.HTTPError as e:
            self._consecutive_failures += 1
            if e.response.status_code == 429:
                raise ShureAPIRateLimitError(
                    message=f"Rate limit exceeded for {method} {url}", response=e.response
                ) from e
            logger.error(
                "API HTTP error: %s %s - Status %d: %s",
                method,
                url,
                e.response.status_code,
                e.response.text[:200],  # Limit error text length
            )
            raise ShureAPIError(
                message=f"HTTP error for {method} {url}",
                status_code=e.response.status_code,
                response=e.response,
            ) from e
        except requests.exceptions.ConnectionError as e:
            self._consecutive_failures += 1
            self._is_healthy = False
            logger.error("API connection error: %s %s - %s", method, url, e)
            raise ShureAPIError(f"Connection error to {url}", response=None) from e
        except requests.exceptions.Timeout as e:
            self._consecutive_failures += 1
            logger.error("API timeout error: %s %s - %s", method, url, e)
            raise ShureAPIError(f"Timeout error for {url}", response=None) from e
        except requests.RequestException as e:
            self._consecutive_failures += 1
            logger.error("API request failed: %s %s - %s", method, url, e)
            raise ShureAPIError(f"Unknown request error for {url}", response=None) from e
        except json.JSONDecodeError as e:
            self._consecutive_failures += 1
            logger.error("Failed to parse JSON response from %s %s: %s", method, url, e)
            raise ShureAPIError(f"Invalid JSON response from {url}", response=None) from e

    @rate_limit(calls_per_second=5.0)
    def get_devices(self) -> list[dict]:
        """Get list of all devices from Shure System API"""
        result = self._make_request("GET", "/api/v1/devices")
        return result if isinstance(result, list) else []

    @rate_limit(calls_per_second=10.0)
    def get_device(self, device_id: str) -> dict | None:
        """Get detailed data for a specific device"""
        return self._make_request("GET", f"/api/v1/devices/{device_id}")

    @rate_limit(calls_per_second=10.0)
    def get_device_channels(self, device_id: str) -> list[dict]:
        """Get channel data for a device"""
        result = self._make_request("GET", f"/api/v1/devices/{device_id}/channels")
        return result if isinstance(result, list) else []

    @rate_limit(calls_per_second=10.0)
    def get_transmitter_data(self, device_id: str, channel: int) -> dict | None:
        """Get transmitter data for a specific channel"""
        return self._make_request("GET", f"/api/v1/devices/{device_id}/channels/{channel}/tx")

    def poll_all_devices(self) -> dict[str, dict]:
        """Poll all devices and return aggregated data with transmitter info"""
        try:
            devices = self.get_devices()
            logger.info("Polling %d devices from Shure System API", len(devices))
        except ShureAPIError:
            logger.exception("Failed to get device list")
            return {}

        data = {}
        for device in devices:
            device_id = device.get("id")
            if not device_id:
                logger.warning("Device missing 'id' field: %s", device)
                continue

            try:
                device_data = self.get_device(device_id)
                if not device_data:
                    logger.warning("No data returned for device %s", device_id)
                    continue

                # Optional enrichment from additional endpoints (best-effort)
                try:
                    device_data = self._enrich_device_data(device_id, device_data)
                except Exception:
                    logger.debug("Enrichment failed for device %s", device_id)

                # Get channel/transmitter data
                channels = self.get_device_channels(device_id)
                device_data["channels"] = channels

                # Transform to micboard format
                transformed = self._transform_device_data(device_data)
                if transformed:
                    data[device_id] = transformed
                else:
                    logger.warning("Failed to transform data for device %s", device_id)
            except ShureAPIError:
                logger.exception("Error polling device %s", device_id)
                continue

        # Firmware coverage validation
        missing_fw = [d for d in data.values() if not d.get("firmware")]
        if missing_fw:
            logger.warning("%d devices missing firmware info", len(missing_fw))
        else:
            logger.info("Firmware info present for all devices")

        logger.info("Successfully polled %d devices", len(data))
        return data

    def _transform_device_data(self, api_data: dict) -> dict | None:
        """Transform Shure API format to micboard format with comprehensive error handling."""
        try:
            device_id = api_data.get("id")
            if not device_id:
                logger.error("Device data missing 'id' field")
                return None

            identity = self.identify_device_model(api_data)
            device_type = identity["type"]
            logger.debug(
                "Transforming device %s (type: %s, model: %s)",
                device_id,
                device_type,
                identity.get("model"),
            )

            result = {
                "id": device_id,
                "ip": api_data.get("ip_address", api_data.get("ipAddress", "")),
                "type": device_type,
                "name": identity.get("model", ""),
                "firmware": identity.get("firmware", ""),
                # Additional device details (populated if present or via enrichment)
                "serial": api_data.get("serial_number", api_data.get("serialNumber")),
                "hostname": api_data.get("hostname"),
                "mac_address": api_data.get("mac_address", api_data.get("macAddress")),
                "model_variant": api_data.get("model_variant", api_data.get("modelVariant")),
                "band": api_data.get("frequency_band", api_data.get("frequencyBand")),
                "location": api_data.get("location"),
                # Best-effort extra info bucket for consumers that want more detail
                "info": {
                    "raw_type": identity.get("raw_type", ""),
                    "raw_model": identity.get("raw_model", ""),
                    "uptime_minutes": api_data.get("uptime_minutes", api_data.get("uptimeMinutes")),
                    "temperature_c": api_data.get("temperature_c", api_data.get("temperatureC")),
                },
                "channels": [],
            }

            # Transform channel data
            channels_data = api_data.get("channels", [])
            logger.debug("Processing %d channels for device %s", len(channels_data), device_id)

            for channel_data in channels_data:
                channel_num = channel_data.get("channel", channel_data.get("channelNumber", 0))
                tx_data = channel_data.get("tx", channel_data.get("transmitter", {}))

                # Only add channel if transmitter data exists
                if tx_data and isinstance(tx_data, dict):
                    transformed_tx = self._transform_transmitter_data(tx_data, channel_num)
                    if transformed_tx:
                        result["channels"].append(
                            {
                                "channel": channel_num,
                                "tx": transformed_tx,
                            }
                        )
                else:
                    logger.debug(
                        "No transmitter data for device %s channel %d",
                        device_id,
                        channel_num,
                    )

            logger.debug(
                "Successfully transformed device %s with %d channels",
                device_id,
                len(result["channels"]),
            )
            return result
        except Exception:
            logger.exception("Error transforming device data for device %s", api_data.get("id"))
            return None

    def identify_device_model(self, api_data: dict) -> dict:
        """Identify and normalize device model information from Shure System API payload.

        Returns a dict with keys:
        - model: Human-readable model name (e.g., 'ULX-D', 'QLX-D')
        - type: Normalized family key used by micboard (e.g., 'ulxd', 'qlxd')
        - firmware: Firmware version string (if available)
        - raw_type: Raw API 'type' value (if available)
        - raw_model: Raw API model field value (if available)
        """
        raw_type = api_data.get("type")
        raw_model = api_data.get("model_name", api_data.get("modelName"))
        firmware = api_data.get("firmware_version", api_data.get("firmwareVersion")) or ""

        norm_type = self._map_device_type(raw_type or "unknown")

        # Derive a friendly model label if Shure provides nothing
        if not raw_model:
            fallback_model = {
                "ulxd": "ULX-D",
                "qlxd": "QLX-D",
                "uhfr": "UHF-R",
                "axtd": "Axient Digital",
                "p10t": "P10T",
            }.get(norm_type, "Unknown")
            model = fallback_model
        else:
            model = str(raw_model)

        return {
            "model": model,
            "type": norm_type,
            "firmware": str(firmware),
            "raw_type": raw_type or "",
            "raw_model": raw_model or "",
        }

    def _transform_transmitter_data(self, tx_data: dict, channel_num: int) -> dict | None:
        """Transform transmitter data from Shure API format to micboard format.

        Handles various field name variations and provides sensible defaults.
        """
        try:
            # Battery data - handle both 'bars' and 'charge' formats
            battery_bars = tx_data.get("battery_bars", tx_data.get("batteryBars", 255))
            battery_charge = tx_data.get("battery_charge", tx_data.get("batteryCharge"))
            battery_runtime = tx_data.get(
                "battery_runtime_minutes", tx_data.get("batteryRuntimeMinutes")
            )

            # Audio and RF levels
            audio_level = tx_data.get("audio_level", tx_data.get("audioLevel", 0))
            rf_level = tx_data.get("rf_level", tx_data.get("rfLevel", 0))

            # Frequency and antenna
            frequency = tx_data.get("frequency", "")
            antenna = tx_data.get("antenna", "")

            # Status and quality
            status = tx_data.get("status", "")
            quality = tx_data.get("audio_quality", tx_data.get("audioQuality", 255))
            tx_offset = tx_data.get("tx_offset", tx_data.get("txOffset", 255))

            # Transmitter name
            name = tx_data.get("name", tx_data.get("deviceName", ""))

            # Slot assignment - use channel number if not explicitly provided
            slot = tx_data.get("slot", channel_num)

            # Optional extra details not required by core micboard views
            extra = {
                "encryption": tx_data.get("encryption"),
                "rf_quality": tx_data.get("rf_quality", tx_data.get("rfQuality")),
                "diversity": tx_data.get("diversity"),
                "antenna_metrics": {
                    "a": tx_data.get("rfAntennaA", tx_data.get("rf_antenna_a")),
                    "b": tx_data.get("rfAntennaB", tx_data.get("rf_antenna_b")),
                },
                "clip": tx_data.get("clip"),
                "peak": tx_data.get("peak"),
                "battery_health": tx_data.get("battery_health", tx_data.get("batteryHealth")),
                "battery_cycles": tx_data.get("battery_cycles", tx_data.get("batteryCycles")),
                "battery_temperature_c": tx_data.get(
                    "battery_temperature_c", tx_data.get("batteryTemperatureC")
                ),
            }

            return {
                "battery": battery_bars,
                "battery_charge": battery_charge,
                "audio_level": audio_level,
                "rf_level": rf_level,
                "frequency": str(frequency) if frequency else "",
                "antenna": str(antenna) if antenna else "",
                "tx_offset": tx_offset,
                "quality": quality,
                "runtime": self._format_runtime(battery_runtime),
                "status": str(status) if status else "",
                # Additional transmitter details when available
                "mute": tx_data.get("mute", tx_data.get("isMuted")),
                "power": tx_data.get("power", tx_data.get("txPower")),
                "battery_type": tx_data.get("battery_type", tx_data.get("batteryType")),
                "temperature": tx_data.get("temperature"),
                "rf_antenna_a": tx_data.get("rfAntennaA", tx_data.get("rf_antenna_a")),
                "rf_antenna_b": tx_data.get("rfAntennaB", tx_data.get("rf_antenna_b")),
                "name": str(name) if name else "",
                "name_raw": str(name) if name else "",
                "slot": slot,
                "extra": extra,
            }
        except Exception:
            logger.exception("Error transforming transmitter data for channel %d", channel_num)
            return None

    # --- Optional enrichment endpoints (best-effort) ---
    def get_device_identity(self, device_id: str) -> dict | None:
        """Fetch device identity info if the endpoint exists."""
        try:
            return self._make_request("GET", f"/api/v1/devices/{device_id}/identify")
        except ShureAPIError:
            logger.debug("Identity endpoint not available for device %s", device_id)
            return None

    def get_device_network(self, device_id: str) -> dict | None:
        """Fetch device network info (hostname, MAC) if available."""
        try:
            return self._make_request("GET", f"/api/v1/devices/{device_id}/network")
        except ShureAPIError:
            logger.debug("Network endpoint not available for device %s", device_id)
            return None

    def get_device_status(self, device_id: str) -> dict | None:
        """Fetch general device status details if available."""
        try:
            return self._make_request("GET", f"/api/v1/devices/{device_id}/status")
        except ShureAPIError:
            logger.debug("Status endpoint not available for device %s", device_id)
            return None

    def _enrich_device_data(self, device_id: str, device_data: dict) -> dict:
        """Best-effort enrichment of device data from optional endpoints.

        Merges fields like serial number, hostname, MAC, model variant, band, and location when available.
        """
        identity = self.get_device_identity(device_id)
        if identity and isinstance(identity, dict):
            device_data.setdefault("serial_number", identity.get("serialNumber"))
            device_data.setdefault("model_variant", identity.get("modelVariant"))
            fw = identity.get("firmwareVersion")
            if fw:
                device_data["firmware_version"] = fw

        net = self.get_device_network(device_id)
        if net and isinstance(net, dict):
            device_data.setdefault("hostname", net.get("hostname"))
            device_data.setdefault("mac_address", net.get("macAddress"))

        status = self.get_device_status(device_id)
        if status and isinstance(status, dict):
            device_data.setdefault("frequency_band", status.get("frequencyBand"))
            device_data.setdefault("location", status.get("location"))

        return device_data

    @staticmethod
    def _map_device_type(api_type: str) -> str:
        """Map Shure API device types to micboard types.

        Handles various naming conventions from the Shure System API.
        """
        if not api_type:
            return "unknown"

        api_type_upper = api_type.upper().replace("-", "_").replace(" ", "_")

        type_map = {
            "UHFR": "uhfr",
            "UHF_R": "uhfr",
            "QLXD": "qlxd",
            "QLX_D": "qlxd",
            "ULXD": "ulxd",
            "ULX_D": "ulxd",
            "AXIENT_DIGITAL": "axtd",
            "AXIENTDIGITAL": "axtd",
            "AXTD": "axtd",
            "AD": "axtd",
            "P10T": "p10t",
            "PSM1000": "p10t",
        }
        return type_map.get(api_type_upper, "unknown")

    @staticmethod
    def _format_runtime(minutes: int | None) -> str:
        """Format battery runtime from minutes to HH:MM format."""
        if minutes is None or minutes < 0:
            return ""
        try:
            hours = int(minutes) // 60
            mins = int(minutes) % 60
            return f"{hours:02d}:{mins:02d}"
        except (ValueError, TypeError):
            return ""

    async def connect_and_subscribe(self, device_id: str, callback) -> None:
        """Establishes WebSocket connection and subscribes to device updates.

        Args:
            device_id: The Shure API device ID to subscribe to
            callback: Function to call with received WebSocket messages

        Raises:
            ShureAPIError: If connection or subscription fails
        """
        if not self.websocket_url:
            logger.error("Shure API WebSocket URL not configured")
            raise ShureAPIError("Shure API WebSocket URL not configured")

        try:
            async with websockets.connect(self.websocket_url, ssl=self.verify_ssl) as websocket:
                logger.info("Connected to Shure API WebSocket: %s", self.websocket_url)

                # First message from WebSocket is usually the transportId
                message = await websocket.recv()
                logger.debug("Received initial WebSocket message: %s", message[:200])

                try:
                    transport_id_data = json.loads(message)
                    transport_id = transport_id_data.get("transportId")
                except json.JSONDecodeError:
                    logger.exception("Failed to parse WebSocket transport ID message")
                    raise ShureAPIError("Invalid WebSocket transport ID message") from None

                if not transport_id:
                    logger.error("Missing transportId in WebSocket message: %s", message[:200])
                    raise ShureAPIError("Failed to get transportId from WebSocket")

                logger.info("Received transportId: %s", transport_id)

                # Subscribe to device updates using the REST API with the transportId
                subscribe_endpoint = (
                    f"/api/v1/devices/{device_id}/identify/subscription/{transport_id}"
                )
                try:
                    # This is a POST request to the REST API, not over the WebSocket
                    subscribe_response = self._make_request("POST", subscribe_endpoint)
                    if subscribe_response and subscribe_response.get("status") == "success":
                        logger.info("Successfully subscribed to device %s updates", device_id)
                    else:
                        logger.error(
                            "Failed to subscribe to device %s: %s",
                            device_id,
                            subscribe_response,
                        )
                        raise ShureAPIError(f"Failed to subscribe to device {device_id} updates")
                except ShureAPIError:
                    logger.exception("Error during REST subscription for device %s", device_id)
                    raise

                # Continuously receive messages from the WebSocket
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        logger.debug("Received WebSocket message for device %s", device_id)
                        callback(data)  # Pass the received data to the callback
                    except json.JSONDecodeError:
                        logger.exception("Failed to parse WebSocket message: %s", message[:200])
                        continue  # Skip invalid messages but keep connection alive
                    except Exception:
                        logger.exception("Error processing WebSocket message")
                        continue  # Don't let callback errors kill the connection

        except websockets.exceptions.ConnectionClosedOK:
            logger.info("Shure API WebSocket connection closed gracefully for device %s", device_id)
        except websockets.exceptions.ConnectionClosedError:
            logger.exception(
                "Shure API WebSocket connection closed with error for device %s", device_id
            )
            raise ShureAPIError(f"WebSocket connection error for device {device_id}") from None
        except Exception:
            logger.exception(
                "Unhandled error in Shure API WebSocket connection for device %s", device_id
            )
            raise ShureAPIError(f"Unhandled WebSocket error for device {device_id}") from None
