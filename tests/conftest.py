import asyncio
import os

import pytest

# Ensure Django settings are set for pytest and VS Code discovery
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session.

    This avoids RuntimeError on some platforms when pytest-asyncio looks for a loop.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
