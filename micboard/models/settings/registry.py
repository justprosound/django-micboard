"""Settings registry models for database-backed configuration."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, ClassVar

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

    def parse_value(self, raw_value: str) -> Any:
        """Parse raw string value according to setting type."""
        if self.setting_type == self.TYPE_STRING:
            return raw_value
        elif self.setting_type == self.TYPE_INTEGER:
            return int(raw_value)
        elif self.setting_type == self.TYPE_BOOLEAN:
            return raw_value.lower() in ("true", "1", "yes", "on")
        elif self.setting_type == self.TYPE_JSON:
            return json.loads(raw_value)
        elif self.setting_type == self.TYPE_CHOICES:
            return raw_value
        return raw_value

    def serialize_value(self, value: Any) -> str:
        """Serialize value to string for storage."""
        if self.setting_type == self.TYPE_JSON:
            return json.dumps(value)
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
    organization = models.ForeignKey(
        "micboard.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="settings",
        help_text="Organization if scope is ORGANIZATION",
    )
    site = models.ForeignKey(
        "micboard.Site",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="settings",
        help_text="Site if scope is SITE",
    )
    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="settings",
        help_text="Manufacturer if scope is MANUFACTURER",
    )

    value = models.TextField(
        help_text="Setting value (stored as string, parsed by definition)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Setting"
        verbose_name_plural = "Settings"
        ordering = ["definition", "organization", "site", "manufacturer"]
        # Enforce uniqueness per scope
        unique_together = [
            ["definition", "organization", "site", "manufacturer"],
        ]

    def __str__(self) -> str:
        scope_name = self.organization or self.site or self.manufacturer or "Global"
        return f"{self.definition.label} = {self.value[:50]} ({scope_name})"

    def get_parsed_value(self) -> Any:
        """Get the parsed value according to definition type."""
        return self.definition.parse_value(self.value)

    def set_value(self, value: Any) -> None:
        """Set value and automatically serialize."""
        self.value = self.definition.serialize_value(value)
