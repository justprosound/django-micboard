"""
SSE client for Sennheiser SSCv2 subscriptions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

import requests

from micboard.integrations.sennheiser.client import SennheiserSystemAPIClient

logger = logging.getLogger(__name__)


async def connect_and_subscribe(
    client: SennheiserSystemAPIClient, device_id: str, callback: Callable[[dict[str, Any]], None]
):
    """
    Establish SSE connection and subscribe to Sennheiser device updates.

    Args:
        client: SennheiserSystemAPIClient instance
        device_id: The Sennheiser API device ID to subscribe to
        callback: Function to call with received SSE messages
    """
    # Start subscription
    try:
        response = client._make_request("GET", "/api/ssc/state/subscriptions")
        if not response or not isinstance(response, dict):
            logger.error("Failed to start subscription")
            return

        session_uuid = response.get("sessionUUID")
        if not session_uuid:
            logger.error("No sessionUUID in subscription response")
            return

        logger.info("Started subscription with sessionUUID: %s", session_uuid)

        # Subscribe to device resources
        resources = [f"/api/devices/{device_id}"]
        client._make_request("PUT", f"/api/ssc/state/subscriptions/{session_uuid}", json=resources)

        # Start SSE stream
        sse_url = f"{client.base_url}/api/ssc/state/subscriptions/{session_uuid}"
        headers = {"Authorization": f"Bearer {client.password}"}

        # Use requests with stream=True for SSE
        with requests.get(
            sse_url, headers=headers, stream=True, verify=client.verify_ssl
        ) as response:
            if response.status_code != 200:
                logger.error("SSE connection failed with status %d", response.status_code)
                return

            for line in response.iter_lines():
                if line:
                    line_str = line.decode("utf-8")
                    if line_str.startswith("data: "):
                        data_str = line_str[6:]  # Remove 'data: ' prefix
                        try:
                            data = json.loads(data_str)
                            await callback(data)
                        except json.JSONDecodeError:
                            logger.debug("Invalid JSON in SSE data: %s", data_str)
            return

    except Exception as e:
        logger.exception("Error in SSE subscription: %s", e)
    return
    return
