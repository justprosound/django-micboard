"""Access-control tests for the browser WebSocket consumer."""

from __future__ import annotations

from unittest.mock import AsyncMock, call

from django.contrib.auth.models import AnonymousUser, User
from django.test import override_settings

import pytest
from asgiref.sync import async_to_sync

from micboard.multitenancy.models import Campus, Organization, OrganizationMembership
from micboard.services.notification.realtime_routing_service import (
    GLOBAL_UPDATES_GROUP,
    campus_updates_group,
    organization_updates_group,
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
    return consumer


@override_settings(MICBOARD_MSP_ENABLED=False)
def test_anonymous_connection_is_rejected() -> None:
    consumer = _consumer_for(AnonymousUser())

    async_to_sync(consumer.connect)()

    consumer.close.assert_awaited_once_with(code=UNAUTHENTICATED_CLOSE_CODE)
    consumer.accept.assert_not_awaited()
    consumer.channel_layer.group_add.assert_not_awaited()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=False)
def test_authenticated_non_msp_connection_joins_global_group(regular_user: User) -> None:
    consumer = _consumer_for(regular_user)

    async_to_sync(consumer.connect)()

    consumer.channel_layer.group_add.assert_awaited_once_with(
        GLOBAL_UPDATES_GROUP,
        consumer.channel_name,
    )
    consumer.accept.assert_awaited_once_with()
    consumer.close.assert_not_awaited()


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
