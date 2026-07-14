"""Settings registry models for database-backed configuration."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SettingDefinition(models.Model):
    """Defines a setting that can be configured by admins."""

    SCOPE_GLOBAL = "global"
    SCOPE_ORGANIZATION = "organization"
    SCOPE_SITE = "site"
    SCOPE_MANUFACTURER = "manufacturer"
    SCOPE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (SCOPE_GLOBAL, "Global (applies to all)"),
        (SCOPE_ORGANIZATION, "Organization (MSP mode)"),
        (SCOPE_SITE, "Site (multi-site mode)"),
        (SCOPE_MANUFACTURER, "Manufacturer-specific"),
    ]

    TYPE_STRING = "string"
    TYPE_INTEGER = "integer"
    TYPE_BOOLEAN = "boolean"
    TYPE_JSON = "json"
    TYPE_CHOICES = "choices"
    TYPE_OPTIONS: ClassVar[list[tuple[str, str]]] = [
        (TYPE_STRING, "Text"),
        (TYPE_INTEGER, "Integer"),
        (TYPE_BOOLEAN, "Boolean"),
        (TYPE_JSON, "JSON"),
        (TYPE_CHOICES, "Dropdown"),
    ]

    key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique setting key (e.g., 'battery_low_threshold')",
    )
    label = models.CharField(
        max_length=255,
        help_text="Human-readable label for admin interface",
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of what this setting controls",
    )
    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default=SCOPE_GLOBAL,
        help_text="Whether setting applies globally, per-org, per-site, or per-manufacturer",
    )
    setting_type = models.CharField(
        max_length=20,
        choices=TYPE_OPTIONS,
        default=TYPE_STRING,
        help_text="Data type for this setting",
    )
    default_value = models.TextField(
        help_text="Default value (stored as string)",
    )
    choices_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="For TYPE_CHOICES: {value: label} mapping",
    )
    required = models.BooleanField(
        default=False,
        help_text="Whether this setting must be configured",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Enable/disable this setting without deleting",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Setting Definition"
        verbose_name_plural = "Setting Definitions"
        ordering = ["scope", "key"]

    def __str__(self) -> str:
        return f"{self.label} ({self.key})"

    def clean(self) -> None:
        """Validate defaults and preserve the contract of stored overrides."""
        super().clean()
        errors: dict[str, str] = {}

        if self.setting_type == self.TYPE_CHOICES and (
            not isinstance(self.choices_json, dict) or not self.choices_json
        ):
            errors["choices_json"] = "Choices settings require a non-empty value-to-label mapping"

        try:
            self.parse_value(self.default_value)
        except (AttributeError, TypeError, ValueError) as exc:
            errors["default_value"] = f"Invalid default for {self.setting_type}: {exc}"

        if self.pk is not None:
            self._validate_existing_overrides(errors)

        if errors:
            raise ValidationError(errors)

    def _validate_existing_overrides(self, errors: dict[str, str]) -> None:
        """Reject definition changes that would strand existing overrides."""
        from micboard.services.settings.visibility_service import settings_visibility

        using = self._state.db or "default"
        overrides = (
            Setting.objects.using(using)
            .filter(definition_id=self.pk)
            .only(
                "organization_id",
                "site_id",
                "manufacturer_id",
                "value",
            )
        )
        scope_mismatch = False
        invalid_value = False
        for override in overrides.iterator():
            if not settings_visibility.matches_definition_scope(
                definition_scope=self.scope,
                organization_id=override.organization_id,
                site_id=override.site_id,
                manufacturer_id=override.manufacturer_id,
            ):
                scope_mismatch = True
            try:
                self.parse_value(override.value)
            except (AttributeError, TypeError, ValueError):
                invalid_value = True

        if scope_mismatch:
            errors["scope"] = (
                "Existing overrides target another scope; remove or migrate them before "
                "changing scope"
            )
        if invalid_value:
            errors["setting_type"] = (
                "Existing overrides are incompatible with this type or choices mapping"
            )

    def parse_value(self, raw_value: str) -> Any:
        """Parse raw string value according to setting type."""
        if self.setting_type == self.TYPE_STRING:
            return raw_value
        elif self.setting_type == self.TYPE_INTEGER:
            return int(raw_value)
        elif self.setting_type == self.TYPE_BOOLEAN:
            normalized = raw_value.lower()
            if normalized in ("true", "1", "yes", "on"):
                return True
            if normalized in ("false", "0", "no", "off"):
                return False
            raise ValueError("enter true, false, 1, 0, yes, no, on, or off")
        elif self.setting_type == self.TYPE_JSON:
            return json.loads(raw_value)
        elif self.setting_type == self.TYPE_CHOICES:
            if not isinstance(self.choices_json, dict) or raw_value not in self.choices_json:
                raise ValueError("select a key present in choices JSON")
            return raw_value
        return raw_value

    def serialize_value(self, value: Any) -> str:
        """Serialize value to string for storage."""
        if self.setting_type == self.TYPE_JSON:
            return json.dumps(value)
        elif self.setting_type == self.TYPE_BOOLEAN:
            return "true" if value else "false"
        return str(value)


class Setting(models.Model):
    """Actual setting values, scoped by organization/site/manufacturer."""

    definition = models.ForeignKey(
        SettingDefinition,
        on_delete=models.CASCADE,
        related_name="values",
        help_text="Which setting this defines",
    )

    # Scope identifiers (at least one should be set)
    # Note: ForeignKey references are commented out to avoid app_registry conflicts during migrations
    # These will be enabled once all related apps are fully loaded and tested
    organization_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Organization ID if scope is ORGANIZATION",
    )
    site = models.ForeignKey(
        "sites.Site",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="settings",
        help_text="Site if scope is SITE",
    )
    manufacturer_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Manufacturer ID if scope is MANUFACTURER",
    )

    value = models.TextField(
        help_text="Setting value (stored as string, parsed by definition)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Setting"
        verbose_name_plural = "Settings"
        ordering = ["definition", "organization_id", "site", "manufacturer_id"]
        unique_together: ClassVar[list[list[str]]] = [
            ["definition", "organization_id", "site", "manufacturer_id"]
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        organization_id__isnull=True,
                        site__isnull=True,
                        manufacturer_id__isnull=True,
                    )
                    | models.Q(
                        organization_id__isnull=False,
                        site__isnull=True,
                        manufacturer_id__isnull=True,
                    )
                    | models.Q(
                        organization_id__isnull=True,
                        site__isnull=False,
                        manufacturer_id__isnull=True,
                    )
                    | models.Q(
                        organization_id__isnull=True,
                        site__isnull=True,
                        manufacturer_id__isnull=False,
                    )
                ),
                name="setting_exactly_one_scope",
            ),
            models.UniqueConstraint(
                fields=["definition"],
                condition=models.Q(
                    organization_id__isnull=True,
                    site__isnull=True,
                    manufacturer_id__isnull=True,
                ),
                name="setting_unique_global",
            ),
            models.UniqueConstraint(
                fields=["definition", "organization_id"],
                condition=models.Q(
                    organization_id__isnull=False,
                    site__isnull=True,
                    manufacturer_id__isnull=True,
                ),
                name="setting_unique_organization",
            ),
            models.UniqueConstraint(
                fields=["definition", "site"],
                condition=models.Q(
                    organization_id__isnull=True,
                    site__isnull=False,
                    manufacturer_id__isnull=True,
                ),
                name="setting_unique_site",
            ),
            models.UniqueConstraint(
                fields=["definition", "manufacturer_id"],
                condition=models.Q(
                    organization_id__isnull=True,
                    site__isnull=True,
                    manufacturer_id__isnull=False,
                ),
                name="setting_unique_manufacturer",
            ),
        ]

    def __str__(self) -> str:
        scope_name = self.organization_id or self.site or self.manufacturer_id or "Global"
        return f"{self.definition.label} ({scope_name})"

    def get_parsed_value(self) -> Any:
        """Get the parsed value according to definition type."""
        return self.definition.parse_value(self.value)

    def clean(self) -> None:
        """Require one target matching the definition's declared scope."""
        super().clean()
        from micboard.services.settings.visibility_service import settings_visibility

        if not settings_visibility.matches_definition_scope(
            definition_scope=self.definition.scope,
            organization_id=self.organization_id,
            site_id=self.site_id,
            manufacturer_id=self.manufacturer_id,
        ):
            raise ValidationError(
                "The configured target must match the setting definition's declared scope"
            )

    def set_value(self, value: Any) -> None:
        """Set value and automatically serialize."""
        self.value = self.definition.serialize_value(value)
