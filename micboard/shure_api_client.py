import logging
import time
from functools import wraps
from typing import Any, Callable, Optional

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
        status_code: Optional[int] = None,
        response: Optional[requests.Response] = None,
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
        retry_after: Optional[int] = None,
        response: Optional[requests.Response] = None,
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
                logger.debug(f"Rate limiting {func.__name__}: sleeping {sleep_time:.3f}s")
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

        # Create session with retry strategy
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.retry_backoff,
            status_forcelist=self.retry_status_codes,
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if self.username and self.password:
            self.session.auth = (self.username, self.password)

        self.websocket_url = config.get("SHURE_API_WEBSOCKET_URL")
        if not self.websocket_url:
            # Infer from base_url if not explicitly set
            ws_scheme = "wss" if self.base_url.startswith("https") else "ws"
            self.websocket_url = f"{ws_scheme}://{self.base_url.split('://', 1)[1]}/api/v1/subscriptions/websocket/create"

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Any]:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify_ssl)

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                raise ShureAPIRateLimitError(
                    message=f"Rate limit exceeded for {method} {url}", response=e.response
                ) from e
            logger.error(
                f"API HTTP error: {method} {url} - {e.response.status_code} {e.response.text}"
            )
            raise ShureAPIError(
                message=f"HTTP error for {method} {url}",
                status_code=e.response.status_code,
                response=e.response,
            ) from e
        except requests.exceptions.ConnectionError as e:
            logger.error(f"API connection error: {method} {url} - {e}")
            raise ShureAPIError(f"Connection error to {url}", response=None) from e
        except requests.exceptions.Timeout as e:
            logger.error(f"API timeout error: {method} {url} - {e}")
            raise ShureAPIError(f"Timeout error for {url}", response=None) from e
        except requests.RequestException as e:
            logger.error(f"API request failed: {method} {url} - {e}")
            raise ShureAPIError(f"Unknown request error for {url}", response=None) from e

    @rate_limit(calls_per_second=5.0)
    def get_devices(self) -> list[dict]:
        """Get list of all devices from Shure System API"""
        result = self._make_request("GET", "/api/v1/devices")
        return result if isinstance(result, list) else []

    @rate_limit(calls_per_second=10.0)
    def get_device(self, device_id: str) -> Optional[dict]:
        """Get detailed data for a specific device"""
        return self._make_request("GET", f"/api/v1/devices/{device_id}")

    @rate_limit(calls_per_second=10.0)
    def get_device_channels(self, device_id: str) -> list[dict]:
        """Get channel data for a device"""
        result = self._make_request("GET", f"/api/v1/devices/{device_id}/channels")
        return result if isinstance(result, list) else []

    @rate_limit(calls_per_second=10.0)
    def get_transmitter_data(self, device_id: str, channel: int) -> Optional[dict]:
        """Get transmitter data for a specific channel"""
        return self._make_request("GET", f"/api/v1/devices/{device_id}/channels/{channel}/tx")

    def poll_all_devices(self) -> dict[str, dict]:
        """Poll all devices and return aggregated data with transmitter info"""
        devices = self.get_devices()
        data = {}

        for device in devices:
            device_id = device.get("id")
            if not device_id:
                continue

            device_data = self.get_device(device_id)
            if not device_data:
                continue

            # Get channel/transmitter data
            channels = self.get_device_channels(device_id)
            device_data["channels"] = channels

            # Transform to micboard format
            transformed = self._transform_device_data(device_data)
            if transformed:
                data[device_id] = transformed

        return data

    def _transform_device_data(self, api_data: dict) -> Optional[dict]:
        """Transform Shure API format to micboard format"""
        try:
            device_id = api_data.get("id")
            device_type = self._map_device_type(api_data.get("type", "unknown"))

            result = {
                "id": device_id,
                "ip": api_data.get("ip_address", ""),
                "type": device_type,
                "name": api_data.get("model_name", ""),
                "firmware": api_data.get("firmware_version", ""),
                "channels": [],
            }

            # Transform channel data
            for channel_data in api_data.get("channels", []):
                channel_num = channel_data.get("channel", 0)
                tx_data = channel_data.get("tx", {})

                if tx_data:
                    result["channels"].append(
                        {
                            "channel": channel_num,
                            "tx": {
                                "battery": tx_data.get("battery_bars", 255),
                                "battery_charge": tx_data.get("battery_charge", 0),
                                "audio_level": tx_data.get("audio_level", 0),
                                "rf_level": tx_data.get("rf_level", 0),
                                "frequency": tx_data.get("frequency", ""),
                                "antenna": tx_data.get("antenna", ""),
                                "tx_offset": tx_data.get("tx_offset", 255),
                                "quality": tx_data.get("audio_quality", 255),
                                "runtime": self._format_runtime(
                                    tx_data.get("battery_runtime_minutes")
                                ),
                                "status": tx_data.get("status", ""),
                                "name": tx_data.get("name", ""),
                                "name_raw": tx_data.get("name", ""),
                                "slot": tx_data.get("slot"),  # Added slot here
                            },
                        }
                    )

            return result
        except Exception as e:
            logger.error(f"Error transforming device data: {e}")
            return None

    @staticmethod
    def _map_device_type(api_type: str) -> str:
        """Map Shure API device types to micboard types"""
        type_map = {
            "UHFR": "uhfr",
            "QLXD": "qlxd",
            "ULXD": "ulxd",
            "AXIENT_DIGITAL": "axtd",
            "P10T": "p10t",
        }
        return type_map.get(api_type.upper(), "unknown")

    @staticmethod
    def _format_runtime(minutes: Optional[int]) -> str:
        """Format battery runtime from minutes to HH:MM format"""
        if minutes is None or minutes < 0:
            return ""
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}"

    async def connect_and_subscribe(self, device_id: str, callback: Callable[[dict], None]):
        """Establishes WebSocket connection and subscribes to device updates."""
        if not self.websocket_url:
            logger.error("Shure API WebSocket URL not configured.")
            raise ShureAPIError("Shure API WebSocket URL not configured.")

        try:
            async with websockets.connect(self.websocket_url, ssl=self.verify_ssl) as websocket:
                logger.info(f"Connected to Shure API WebSocket: {self.websocket_url}")

                # First message from WebSocket is usually the transportId
                message = await websocket.recv()
                transport_id_data = json.loads(message)
                transport_id = transport_id_data.get("transportId")

                if not transport_id:
                    logger.error(f"Failed to get transportId from WebSocket: {message}")
                    raise ShureAPIError("Failed to get transportId from WebSocket.")

                logger.info(f"Received transportId: {transport_id}")

                # Subscribe to device updates using the REST API with the transportId
                subscribe_endpoint = (
                    f"/api/v1/devices/{device_id}/identify/subscription/{transport_id}"
                )
                try:
                    # This is a POST request to the REST API, not over the WebSocket
                    subscribe_response = self._make_request("POST", subscribe_endpoint)
                    if subscribe_response and subscribe_response.get("status") == "success":
                        logger.info(f"Successfully subscribed to device {device_id} updates.")
                    else:
                        logger.error(
                            f"Failed to subscribe to device {device_id} updates: {subscribe_response}"
                        )
                        raise ShureAPIError(f"Failed to subscribe to device {device_id} updates.")
                except ShureAPIError as e:
                    logger.error(f"Error during REST subscription for device {device_id}: {e}")
                    raise  # Re-raise the exception

                # Continuously receive messages from the WebSocket
                async for message in websocket:
                    data = json.loads(message)
                    callback(data)  # Pass the received data to the callback

        except websockets.exceptions.ConnectionClosedOK:
            logger.info("Shure API WebSocket connection closed gracefully.")
        except websockets.exceptions.ConnectionClosedError as e:
            logger.error(f"Shure API WebSocket connection closed with error: {e}")
            raise ShureAPIError(f"WebSocket connection error: {e}") from e
        except Exception as e:
            logger.exception(f"Unhandled error in Shure API WebSocket connection: {e}")
            raise ShureAPIError(f"Unhandled WebSocket error: {e}") from e
