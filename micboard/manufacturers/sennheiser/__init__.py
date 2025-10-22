"""Shim package for `micboard.manufacturers.sennheiser` that forwards to
`micboard.integrations.sennheiser` so legacy imports continue to resolve.
"""

from __future__ import annotations

import importlib
import sys

_target = importlib.import_module("micboard.integrations.sennheiser")
__path__ = list(_target.__path__)
__package__ = "micboard.manufacturers.sennheiser"
sys.modules[__package__] = _target
