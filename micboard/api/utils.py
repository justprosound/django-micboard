"""Helper utilities for API views.

This module provides small, focused helpers used by the API views. Keeping a
module docstring satisfies package-quality checks in the test-suite.
"""

import logging
from typing import Union

from django.http import HttpRequest

logger = logging.getLogger(__name__)


def _get_manufacturer_code(request: HttpRequest) -> Union[str, None]:
    """Safely extract manufacturer code from request.GET ensuring it's a string."""
    try:
        code = getattr(request, "GET", {}).get("manufacturer")
    except Exception:
        logger.exception("Error extracting manufacturer code from request")
        return None
    return code if isinstance(code, str) else None
