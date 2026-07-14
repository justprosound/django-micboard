"""Import-boundary tests for the pluggable Shure integration."""

from __future__ import annotations

import importlib


def test_shure_client_imports_directly() -> None:
    """The concrete client must not depend cyclically on its sub-clients."""
    client = importlib.import_module("micboard.integrations.shure.client")
    exceptions = importlib.import_module("micboard.integrations.shure.exceptions")

    assert client.ShureAPIError is exceptions.ShureAPIError
    assert client.ShureAPIRateLimitError is exceptions.ShureAPIRateLimitError
    assert client.ShureSystemAPIClient.__module__ == "micboard.integrations.shure.client"
