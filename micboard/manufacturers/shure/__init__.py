"""Shim package for `micboard.manufacturers.shure` that forwards to
`micboard.integrations.shure` so legacy imports continue to resolve.
"""

from __future__ import annotations

import importlib
import sys

_target = importlib.import_module("micboard.integrations.shure")
# Use the integrations package path so submodule imports (e.g. .client)
# continue to work when imported via micboard.manufacturers.shure.*
__path__ = list(_target.__path__)
__package__ = "micboard.manufacturers.shure"

# Ensure sys.modules contains the target under both names
sys.modules[__package__] = _target
