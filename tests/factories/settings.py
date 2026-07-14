"""Factories for database-backed setting definitions and values."""

from __future__ import annotations

import factory

from micboard.models.settings.registry import Setting, SettingDefinition

from .base import ProjectModelFactory
from .registry import register_factory


@register_factory("micboard.SettingDefinition")
class SettingDefinitionFactory(ProjectModelFactory):
    """Create a global string setting definition."""

    class Meta:
        model = SettingDefinition

    key = factory.Sequence(lambda number: f"factory_setting_{number}")
    label = factory.Sequence(lambda number: f"Factory setting {number}")
    default_value = "factory-default"


@register_factory("micboard.Setting")
class SettingFactory(ProjectModelFactory):
    """Create a value consistent with its global setting definition."""

    class Meta:
        model = Setting

    definition = factory.SubFactory("tests.factories.settings.SettingDefinitionFactory")
    value = "factory-value"
