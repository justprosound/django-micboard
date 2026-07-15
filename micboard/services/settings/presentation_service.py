"""Secret-safe presentation queries for stored setting overrides."""

from __future__ import annotations

from typing import Any, cast

from django.apps import apps

from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.services.settings.visibility_service import settings_visibility


class SettingsPresentationService:
    """Build tenant-scoped contexts without exposing unknown setting values."""

    _DISPLAY_SAFE_KEYS = frozenset(
        {
            "activity_log_retention_days",
            "admin_org_selector",
            "alert_on_device_offline_minutes",
            "allow_cross_org_view",
            "allow_org_switching",
            "api_health_log_retention_days",
            "api_timeout",
            "audit_archive_path",
            "battery_critical_level",
            "battery_good_level",
            "battery_low_level",
            "cache_device_specs_minutes",
            "cache_settings_minutes",
            "cache_timeout",
            "device_limit_warning_threshold",
            "device_max_requests_per_call",
            "discovery_enabled",
            "discovery_interval_minutes",
            "global_device_limit",
            "health_check_interval",
            "log_api_calls",
            "msp_enabled",
            "multi_site_mode",
            "poll_interval",
            "polling_batch_size",
            "polling_enabled",
            "polling_interval_seconds",
            "root_domain",
            "service_sync_log_retention_days",
            "site_isolation",
            "subdomain_routing",
            "supports_discovery_ips",
            "supports_health_check",
            "transmitter_inactivity_seconds",
        }
    )

    @classmethod
    def is_key_sensitive(cls, key: str) -> bool:
        """Fail closed for setting keys not explicitly known to be display-safe."""
        return key.lower() not in cls._DISPLAY_SAFE_KEYS

    @classmethod
    def format_value(cls, definition: SettingDefinition, value: Any) -> str:
        """Format one value without exposing unknown or sensitive definitions."""
        if value is None:
            return "—"
        if cls.is_key_sensitive(definition.key):
            return "••••••"
        return str(value)

    @staticmethod
    def _resolve_organization_names(organization_ids: set[int]) -> dict[int, str]:
        """Resolve organization IDs when the optional tenant app is active."""
        if not apps.is_installed("micboard.multitenancy"):
            return {}

        from micboard.multitenancy.models import Organization

        return dict(
            Organization._default_manager.filter(id__in=organization_ids).values_list(
                "id",
                "name",
            )
        )

    @staticmethod
    def _resolve_manufacturer_names(manufacturer_ids: set[int]) -> dict[int, str]:
        """Resolve manufacturer identifiers for visible overrides."""
        from micboard.models.discovery.manufacturer import Manufacturer

        return dict(Manufacturer.objects.filter(id__in=manufacturer_ids).values_list("id", "name"))

    def get_diff(self, *, user: Any) -> dict[str, Any]:
        """Show only setting overrides the requesting user may inspect."""
        scope = settings_visibility.for_user(user=user)
        definitions = list(
            SettingDefinition.objects.filter(is_active=True).order_by(
                "scope",
                "key",
            )
        )
        scoped_settings = (
            Setting.objects.filter(definition__in=definitions)
            .filter(settings_visibility.build_filter(scope))
            .select_related("definition", "site")
        )

        global_settings: dict[int, Setting] = {}
        organization_overrides: dict[int, list[Setting]] = {}
        site_overrides: dict[int, list[Setting]] = {}
        manufacturer_overrides: dict[int, list[Setting]] = {}
        for item in scoped_settings.order_by("definition_id", "pk"):
            if item.organization_id is not None:
                organization_overrides.setdefault(item.definition_id, []).append(item)
            elif item.site_id is not None:
                site_overrides.setdefault(item.definition_id, []).append(item)
            elif item.manufacturer_id is not None:
                manufacturer_overrides.setdefault(item.definition_id, []).append(item)
            else:
                global_settings.setdefault(item.definition_id, item)

        visible_organization_ids = {
            item.organization_id
            for items in organization_overrides.values()
            for item in items
            if item.organization_id is not None
        }
        visible_manufacturer_ids = {
            item.manufacturer_id
            for items in manufacturer_overrides.values()
            for item in items
            if item.manufacturer_id is not None
        }
        organization_names = self._resolve_organization_names(visible_organization_ids)
        manufacturer_names = self._resolve_manufacturer_names(visible_manufacturer_ids)

        overrides: list[dict[str, Any]] = []
        for definition in definitions:
            definition_organization_overrides = organization_overrides.get(definition.pk, [])
            definition_site_overrides = site_overrides.get(definition.pk, [])
            definition_manufacturer_overrides = manufacturer_overrides.get(definition.pk, [])
            if not (
                definition_organization_overrides
                or definition_site_overrides
                or definition_manufacturer_overrides
            ):
                continue

            global_setting = global_settings.get(definition.pk)
            overrides.append(
                {
                    "key": definition.key,
                    "label": definition.label,
                    "global": self.format_value(
                        definition,
                        global_setting.get_parsed_value() if global_setting else None,
                    ),
                    "org_overrides": [
                        {
                            "label": organization_names.get(
                                cast(int, item.organization_id),
                                f"Org {item.organization_id}",
                            ),
                            "value": self.format_value(
                                definition,
                                item.get_parsed_value(),
                            ),
                        }
                        for item in definition_organization_overrides
                    ],
                    "site_overrides": [
                        {
                            "label": item.site.name if item.site else f"Site {item.site_id}",
                            "value": self.format_value(
                                definition,
                                item.get_parsed_value(),
                            ),
                        }
                        for item in definition_site_overrides
                    ],
                    "mfg_overrides": [
                        {
                            "label": manufacturer_names.get(
                                cast(int, item.manufacturer_id),
                                f"Manufacturer {item.manufacturer_id}",
                            ),
                            "value": self.format_value(
                                definition,
                                item.get_parsed_value(),
                            ),
                        }
                        for item in definition_manufacturer_overrides
                    ],
                }
            )

        return {
            "title": "Settings Overrides Diff",
            "overrides": overrides,
        }

    @staticmethod
    def get_overview(*, user: Any) -> dict[str, Any]:
        """Group visible setting metadata by scope without returning raw values."""
        visible_settings = Setting.objects.filter(
            settings_visibility.build_filter(settings_visibility.for_user(user=user))
        )
        return {
            "title": "Settings Overview",
            "global_settings": visible_settings.filter(
                organization_id__isnull=True,
                site__isnull=True,
                manufacturer_id__isnull=True,
            ).select_related("definition"),
            "org_settings": visible_settings.filter(
                organization_id__isnull=False,
            ).select_related("definition"),
            "site_settings": visible_settings.filter(
                site__isnull=False,
            ).select_related("definition", "site"),
            "mfg_settings": visible_settings.filter(
                manufacturer_id__isnull=False,
            ).select_related("definition"),
        }


settings_presentation = SettingsPresentationService()
