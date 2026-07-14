"""Load Micboard model domains for Django app discovery.

Model classes are intentionally not re-exported. Import each model from its
defining domain module so dependencies remain explicit.
"""

# Import submodules for Django app registry
from . import (
    audit,
    discovery,
    hardware,
    integrations,
    locations,
    monitoring,
    realtime,
    rf_coordination,
    settings,
    telemetry,
    users,
)
