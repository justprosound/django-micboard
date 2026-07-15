"""Load Micboard model domains for Django app discovery.

Model classes are intentionally not re-exported. Import each model from its
defining domain module so dependencies remain explicit.
"""

# Import defining modules for Django's app registry without package re-exports.
from . import integrations
from .audit import activity_log, configuration_log
from .discovery import configuration, manufacturer, queue, registry
from .hardware import charger, display_wall, wireless_chassis, wireless_unit
from .locations import structure
from .monitoring import alert, group, performer, performer_assignment
from .realtime import connection
from .rf_coordination import compliance, rf_channel
from .settings import registry as settings_registry
from .telemetry import health, sessions
from .users import user_profile, user_views
