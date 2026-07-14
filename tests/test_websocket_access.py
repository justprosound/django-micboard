"""Access-control tests for the browser WebSocket consumer."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, call

from django.contrib.auth.models import AnonymousUser, Permission, User
from django.contrib.sites.models import Site
from django.test import override_settings

import pytest
from asgiref.sync import async_to_sync

from micboard.models.locations.structure import Building, Location
from micboard.models.monitoring.group import MonitoringGroup
from micboard.multitenancy.models import Campus, Organization, OrganizationMembership
from micboard.services.notification.realtime_routing_service import (
    GLOBAL_UPDATES_GROUP,
    RealtimeRoutingService,
    campus_updates_group,
    organization_updates_group,
    site_updates_group,
)
from micboard.websockets.consumers import (
    UNAUTHENTICATED_CLOSE_CODE,
    UNAUTHORIZED_CLOSE_CODE,
    MicboardConsumer,
)


def _consumer_for(user: User | AnonymousUser) -> MicboardConsumer:
    consumer = MicboardConsumer()
    consumer.scope = {"user": user}
    consumer.channel_name = "test-channel"
    consumer.channel_layer = AsyncMock()
    consumer.accept = AsyncMock()
    consumer.close = AsyncMock()
    consumer.send = AsyncMock()
    return consumer


@override_settings(MICBOARD_MSP_ENABLED=False)
def test_anonymous_connection_is_rejected() -> None:
    consumer = _consumer_for(AnonymousUser())

    asyncio.run(consumer.connect())

    consumer.close.assert_awaited_once_with(code=UNAUTHENTICATED_CLOSE_CODE)
    consumer.accept.assert_not_awaited()
    consumer.channel_layer.group_add.assert_not_awaited()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=False)
def test_single_site_monitoring_member_without_global_permission_is_rejected(
    regular_user: User,
) -> None:
    building = Building.objects.create(name="Scoped Building")
    location = Location.objects.create(name="Scoped Rack", building=building)
    monitoring_group = MonitoringGroup.objects.create(name="Scoped Operators")
    monitoring_group.locations.add(location)
    monitoring_group.users.add(regular_user)
    consumer = _consumer_for(regular_user)
    consumer._can_receive_global_updates = AsyncMock(return_value=False)

    assert not RealtimeRoutingService.can_receive_global_updates(regular_user)

    async_to_sync(consumer.connect)()

    consumer._can_receive_global_updates.assert_awaited_once_with(regular_user)
    consumer.close.assert_awaited_once_with(code=UNAUTHORIZED_CLOSE_CODE)
    consumer.accept.assert_not_awaited()
    consumer.channel_layer.group_add.assert_not_awaited()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=False)
def test_single_site_user_with_global_permission_joins_global_group(
    regular_user: User,
) -> None:
    regular_user.user_permissions.add(
        Permission.objects.get(
            codename="view_realtimeconnection",
            content_type__app_label="micboard",
        )
    )
    consumer = _consumer_for(regular_user)
    consumer._can_receive_global_updates = AsyncMock(return_value=True)

    assert RealtimeRoutingService.can_receive_global_updates(regular_user)

    async_to_sync(consumer.connect)()

    consumer._can_receive_global_updates.assert_awaited_once_with(regular_user)
    consumer.channel_layer.group_add.assert_awaited_once_with(
        GLOBAL_UPDATES_GROUP,
        consumer.channel_name,
    )
    consumer.accept.assert_awaited_once_with()
    consumer.close.assert_not_awaited()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True, SITE_ID=7)
def test_authenticated_multisite_connection_joins_only_current_site(regular_user: User) -> None:
    consumer = _consumer_for(regular_user)

    async_to_sync(consumer.connect)()

    consumer.channel_layer.group_add.assert_awaited_once_with(
        site_updates_group(7),
        consumer.channel_name,
    )
    consumer.accept.assert_awaited_once_with()


@pytest.mark.django_db
def test_active_memberships_resolve_to_least_privilege_groups(regular_user: User) -> None:
    organization_wide = Organization.objects.create(name="Organization Wide", slug="org-wide")
    campus_limited = Organization.objects.create(name="Campus Limited", slug="campus-limited")
    inactive_membership = Organization.objects.create(name="Inactive Membership", slug="inactive")
    campus = Campus.objects.create(
        organization=campus_limited,
        name="North Campus",
        slug="north",
    )
    OrganizationMembership.objects.create(user=regular_user, organization=organization_wide)
    OrganizationMembership.objects.create(
        user=regular_user,
        organization=campus_limited,
        campus=campus,
    )
    OrganizationMembership.objects.create(
        user=regular_user,
        organization=inactive_membership,
        is_active=False,
    )

    groups = MicboardConsumer._membership_group_names(regular_user.pk)

    assert groups == (
        organization_updates_group(organization_wide.pk),
        campus_updates_group(campus_limited.pk, campus.pk),
    )
    assert organization_updates_group(campus_limited.pk) not in groups


@pytest.mark.django_db
@override_settings(MICBOARD_MULTI_SITE_MODE=True, SITE_ID=1)
def test_msp_membership_groups_ignore_other_sites(regular_user: User) -> None:
    current_site = Site.objects.get(pk=1)
    other_site = Site.objects.create(domain="other-ws.example.test", name="Other")
    current = Organization.objects.create(name="Current", slug="current-ws", site=current_site)
    other = Organization.objects.create(name="Other", slug="other-ws", site=other_site)
    OrganizationMembership.objects.create(user=regular_user, organization=current)
    OrganizationMembership.objects.create(user=regular_user, organization=other)

    assert MicboardConsumer._membership_group_names(regular_user.pk) == (
        organization_updates_group(current.pk),
    )


@pytest.mark.django_db
def test_inactive_or_inconsistent_tenant_memberships_are_ignored(regular_user: User) -> None:
    inactive_organization = Organization.objects.create(
        name="Inactive Organization",
        slug="inactive-organization",
        is_active=False,
    )
    membership_organization = Organization.objects.create(
        name="Membership Organization",
        slug="membership-organization",
    )
    other_organization = Organization.objects.create(
        name="Other Organization",
        slug="other-organization",
    )
    inactive_campus_organization = Organization.objects.create(
        name="Inactive Campus Organization",
        slug="inactive-campus-organization",
    )
    mismatched_campus = Campus.objects.create(
        organization=other_organization,
        name="Other Campus",
        slug="other-campus",
    )
    inactive_campus = Campus.objects.create(
        organization=inactive_campus_organization,
        name="Inactive Campus",
        slug="inactive-campus",
        is_active=False,
    )
    OrganizationMembership.objects.create(
        user=regular_user,
        organization=inactive_organization,
    )
    OrganizationMembership.objects.create(
        user=regular_user,
        organization=membership_organization,
        campus=mismatched_campus,
    )
    OrganizationMembership.objects.create(
        user=regular_user,
        organization=inactive_campus_organization,
        campus=inactive_campus,
    )

    assert MicboardConsumer._membership_group_names(regular_user.pk) == ()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True)
def test_msp_connection_without_active_membership_is_rejected(regular_user: User) -> None:
    consumer = _consumer_for(regular_user)
    consumer._active_groups_for_user = AsyncMock(return_value=())

    async_to_sync(consumer.connect)()

    consumer.close.assert_awaited_once_with(code=UNAUTHORIZED_CLOSE_CODE)
    consumer.accept.assert_not_awaited()
    consumer.channel_layer.group_add.assert_not_awaited()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True)
def test_msp_superuser_has_no_global_bypass(admin_user: User) -> None:
    consumer = _consumer_for(admin_user)
    consumer._active_groups_for_user = AsyncMock(return_value=())

    async_to_sync(consumer.connect)()

    consumer.close.assert_awaited_once_with(code=UNAUTHORIZED_CLOSE_CODE)
    consumer.accept.assert_not_awaited()
    consumer.channel_layer.group_add.assert_not_awaited()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True)
def test_msp_connection_joins_every_resolved_membership_group(regular_user: User) -> None:
    expected_groups = (
        organization_updates_group(7),
        campus_updates_group(11, 13),
    )
    consumer = _consumer_for(regular_user)
    consumer._active_groups_for_user = AsyncMock(return_value=expected_groups)

    async_to_sync(consumer.connect)()

    assert consumer.channel_layer.group_add.await_args_list == [
        call(expected_groups[0], consumer.channel_name),
        call(expected_groups[1], consumer.channel_name),
    ]
    consumer.accept.assert_awaited_once_with()
    consumer.close.assert_not_awaited()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_MULTI_SITE_MODE=False)
def test_msp_membership_revocation_blocks_next_group_event(regular_user: User) -> None:
    """A connection cannot retain tenant delivery after membership revocation."""
    organization = Organization.objects.create(name="Revoked", slug="revoked-ws")
    membership = OrganizationMembership.objects.create(
        user=regular_user,
        organization=organization,
    )
    consumer = _consumer_for(regular_user)
    joined_group = organization_updates_group(organization.pk)
    consumer._active_groups_for_user = AsyncMock(return_value=(joined_group,))

    asyncio.run(consumer.connect())
    consumer.channel_layer.group_add.assert_awaited_once_with(joined_group, consumer.channel_name)

    membership.is_active = False
    membership.save(update_fields=["is_active"])
    current_groups = MicboardConsumer._current_group_names(regular_user.pk)
    assert joined_group not in current_groups
    consumer._current_groups_for_user = AsyncMock(return_value=current_groups)
    asyncio.run(consumer.device_update({"data": {"id": 1}}))

    consumer.send.assert_not_awaited()
    consumer.channel_layer.group_discard.assert_awaited_once_with(
        joined_group,
        consumer.channel_name,
    )
    consumer.close.assert_awaited_once_with(code=UNAUTHORIZED_CLOSE_CODE)


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=False)
def test_global_permission_revocation_blocks_next_group_event(regular_user: User) -> None:
    """A global stream permission is re-read before each outbound event."""
    permission = Permission.objects.get(
        codename="view_realtimeconnection",
        content_type__app_label="micboard",
    )
    regular_user.user_permissions.add(permission)
    consumer = _consumer_for(regular_user)
    consumer._can_receive_global_updates = AsyncMock(return_value=True)

    asyncio.run(consumer.connect())
    regular_user.user_permissions.remove(permission)
    current_groups = MicboardConsumer._current_group_names(regular_user.pk)
    assert GLOBAL_UPDATES_GROUP not in current_groups
    consumer._current_groups_for_user = AsyncMock(return_value=current_groups)
    asyncio.run(consumer.status_update({"message": "revoked"}))

    consumer.send.assert_not_awaited()
    consumer.channel_layer.group_discard.assert_awaited_once_with(
        GLOBAL_UPDATES_GROUP,
        consumer.channel_name,
    )
    consumer.close.assert_awaited_once_with(code=UNAUTHORIZED_CLOSE_CODE)


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True, SITE_ID=1)
def test_user_deactivation_blocks_next_site_event(regular_user: User) -> None:
    """A stale authenticated scope cannot outlive persisted user deactivation."""
    consumer = _consumer_for(regular_user)
    asyncio.run(consumer.connect())

    User.objects.filter(pk=regular_user.pk).update(is_active=False)
    current_groups = MicboardConsumer._current_group_names(regular_user.pk)
    assert current_groups == ()
    consumer._current_groups_for_user = AsyncMock(return_value=current_groups)
    asyncio.run(consumer.status_update({"message": "revoked"}))

    consumer.send.assert_not_awaited()
    consumer.channel_layer.group_discard.assert_awaited_once_with(
        site_updates_group(1),
        consumer.channel_name,
    )
    consumer.close.assert_awaited_once_with(code=UNAUTHORIZED_CLOSE_CODE)


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True, SITE_ID=1)
def test_user_deactivation_blocks_ping_reply(regular_user: User) -> None:
    """Heartbeat replies use the same event-time authorization check as data."""
    consumer = _consumer_for(regular_user)
    asyncio.run(consumer.connect())

    User.objects.filter(pk=regular_user.pk).update(is_active=False)
    consumer._current_groups_for_user = AsyncMock(return_value=())
    asyncio.run(consumer.receive(text_data='{"command": "ping"}'))

    consumer.send.assert_not_awaited()
    consumer.channel_layer.group_discard.assert_awaited_once_with(
        site_updates_group(1),
        consumer.channel_name,
    )
    consumer.close.assert_awaited_once_with(code=UNAUTHORIZED_CLOSE_CODE)


@pytest.mark.parametrize(
    ("handler_name", "event"),
    [
        (
            "api_health_update",
            {
                "type": "api_health_update",
                "manufacturer_code": "vendor",
                "health_data": {"status": "healthy"},
            },
        ),
        (
            "device_status_update",
            {
                "type": "device_status_update",
                "device_id": 4,
                "status": "online",
            },
        ),
    ],
)
def test_producer_event_handlers_forward_complete_payloads(
    handler_name: str,
    event: dict[str, object],
) -> None:
    """Every producer dispatch type has a matching browser consumer handler."""
    consumer = _consumer_for(AnonymousUser())
    consumer._can_forward_event = AsyncMock(return_value=True)

    async_to_sync(getattr(consumer, handler_name))(event)

    forwarded = json.loads(consumer.send.await_args.kwargs["text_data"])
    assert forwarded == event
