"""Factories for audit-domain models."""

from __future__ import annotations

from django.utils import timezone

import factory

from micboard.models.audit.activity_log import ActivityLog, ServiceSyncLog
from micboard.models.audit.configuration_log import ConfigurationAuditLog
from tests.factories.base import ProjectModelFactory
from tests.factories.registry import register_factory


@register_factory("micboard.ActivityLog")
class ActivityLogFactory(ProjectModelFactory):
    """Create a standalone audit event."""

    class Meta:
        model = ActivityLog

    summary = factory.Sequence(lambda number: f"Factory activity {number}")


@register_factory("micboard.ServiceSyncLog")
class ServiceSyncLogFactory(ProjectModelFactory):
    """Create a completed manufacturer synchronization record."""

    class Meta:
        model = ServiceSyncLog

    service = factory.SubFactory("tests.factories.discovery.ManufacturerFactory")
    sync_type = "full"
    started_at = factory.LazyFunction(timezone.now)
    status = "success"


@register_factory("micboard.ConfigurationAuditLog")
class ConfigurationAuditLogFactory(ProjectModelFactory):
    """Create an audit event for a manufacturer configuration."""

    class Meta:
        model = ConfigurationAuditLog

    configuration = factory.SubFactory("tests.factories.discovery.ManufacturerConfigurationFactory")
    action = ConfigurationAuditLog.Action.CREATE
