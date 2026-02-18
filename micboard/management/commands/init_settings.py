"""Management command to initialize settings registry with definitions."""

from django.core.management.base import BaseCommand

from micboard.models.settings import SettingDefinition
from micboard.services.manufacturer.manufacturer_config_registry import ManufacturerConfigRegistry


class Command(BaseCommand):
    """Initialize settings definitions."""

    help = "Initialize settings definitions with standard configuration options"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset all settings to default state",
        )
        parser.add_argument(
            "--manufacturer-defaults",
            action="store_true",
            help="Initialize manufacturer default settings",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write(self.style.WARNING("Resetting settings..."))
            SettingDefinition.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("✓ Settings reset"))

        self.stdout.write(self.style.HTTP_INFO("Initializing setting definitions..."))
        count = self._initialize_definitions()
        self.stdout.write(self.style.SUCCESS(f"✓ Created {count} setting definitions"))

        if options["manufacturer_defaults"]:
            self.stdout.write(self.style.HTTP_INFO("Initializing manufacturer defaults..."))
            ManufacturerConfigRegistry.initialize_defaults()
            self.stdout.write(self.style.SUCCESS("✓ Manufacturer defaults initialized"))

    def _initialize_definitions(self) -> int:
        """Create all standard setting definitions."""
        definitions = [
            # Battery thresholds
            {
                "key": "battery_good_level",
                "label": "Battery Good Level (%)",
                "description": "Battery level above which device is considered in good condition",
                "scope": SettingDefinition.SCOPE_MANUFACTURER,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "90",
                "required": False,
            },
            {
                "key": "battery_low_level",
                "label": "Battery Low Level (%)",
                "description": "Battery level at which to alert for low battery",
                "scope": SettingDefinition.SCOPE_MANUFACTURER,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "20",
                "required": False,
            },
            {
                "key": "battery_critical_level",
                "label": "Battery Critical Level (%)",
                "description": "Battery level at which device is considered unreliable",
                "scope": SettingDefinition.SCOPE_MANUFACTURER,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "0",
                "required": False,
            },
            # Health check settings
            {
                "key": "health_check_interval",
                "label": "Health Check Interval (seconds)",
                "description": "How often to check manufacturer API health",
                "scope": SettingDefinition.SCOPE_MANUFACTURER,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "300",
                "required": False,
            },
            # API configuration
            {
                "key": "api_timeout",
                "label": "API Timeout (seconds)",
                "description": "Request timeout for manufacturer API calls",
                "scope": SettingDefinition.SCOPE_MANUFACTURER,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "30",
                "required": False,
            },
            {
                "key": "device_max_requests_per_call",
                "label": "Max Devices Per API Call",
                "description": "Maximum number of devices to request in a single API call",
                "scope": SettingDefinition.SCOPE_MANUFACTURER,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "100",
                "required": False,
            },
            # Feature flags
            {
                "key": "supports_discovery_ips",
                "label": "Supports Discovery IPs",
                "description": "Whether this manufacturer API supports IP-based device discovery",
                "scope": SettingDefinition.SCOPE_MANUFACTURER,
                "setting_type": SettingDefinition.TYPE_BOOLEAN,
                "default_value": "false",
                "required": False,
            },
            {
                "key": "supports_health_check",
                "label": "Supports Health Check API",
                "description": "Whether this manufacturer provides health check endpoints",
                "scope": SettingDefinition.SCOPE_MANUFACTURER,
                "setting_type": SettingDefinition.TYPE_BOOLEAN,
                "default_value": "false",
                "required": False,
            },
            # Discovery settings
            {
                "key": "discovery_enabled",
                "label": "Discovery Enabled",
                "description": "Enable automatic device discovery for this manufacturer",
                "scope": SettingDefinition.SCOPE_ORGANIZATION,
                "setting_type": SettingDefinition.TYPE_BOOLEAN,
                "default_value": "true",
                "required": False,
            },
            {
                "key": "discovery_interval_minutes",
                "label": "Discovery Interval (minutes)",
                "description": "How often to run device discovery",
                "scope": SettingDefinition.SCOPE_ORGANIZATION,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "60",
                "required": False,
            },
            # Polling settings
            {
                "key": "polling_enabled",
                "label": "Polling Enabled",
                "description": "Enable automatic device polling/monitoring",
                "scope": SettingDefinition.SCOPE_ORGANIZATION,
                "setting_type": SettingDefinition.TYPE_BOOLEAN,
                "default_value": "true",
                "required": False,
            },
            {
                "key": "polling_interval_seconds",
                "label": "Polling Interval (seconds)",
                "description": "How often to poll devices for status updates",
                "scope": SettingDefinition.SCOPE_ORGANIZATION,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "300",
                "required": False,
            },
            {
                "key": "polling_batch_size",
                "label": "Polling Batch Size",
                "description": "Number of devices to poll in each batch",
                "scope": SettingDefinition.SCOPE_ORGANIZATION,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "50",
                "required": False,
            },
            # Caching settings
            {
                "key": "cache_device_specs_minutes",
                "label": "Cache Device Specs (minutes)",
                "description": "How long to cache device specifications",
                "scope": SettingDefinition.SCOPE_GLOBAL,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "1440",  # 24 hours
                "required": False,
            },
            {
                "key": "cache_settings_minutes",
                "label": "Cache Settings (minutes)",
                "description": "How long to cache setting values",
                "scope": SettingDefinition.SCOPE_GLOBAL,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "5",
                "required": False,
            },
            # Logging/reporting
            {
                "key": "log_api_calls",
                "label": "Log API Calls",
                "description": "Log details of all manufacturer API calls",
                "scope": SettingDefinition.SCOPE_ORGANIZATION,
                "setting_type": SettingDefinition.TYPE_BOOLEAN,
                "default_value": "false",
                "required": False,
            },
            {
                "key": "alert_on_device_offline_minutes",
                "label": "Alert on Device Offline (minutes)",
                "description": "Send alert if device doesn't respond for this long",
                "scope": SettingDefinition.SCOPE_ORGANIZATION,
                "setting_type": SettingDefinition.TYPE_INTEGER,
                "default_value": "30",
                "required": False,
            },
        ]

        created_count = 0
        for defn_data in definitions:
            defn, created = SettingDefinition.objects.get_or_create(
                key=defn_data["key"],
                defaults=defn_data,
            )
            if created:
                created_count += 1
                self.stdout.write(f"  ✓ Created {defn_data['key']}")
            else:
                self.stdout.write(f"  - Skipped {defn_data['key']} (already exists)")

        return created_count
