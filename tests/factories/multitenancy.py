"""Factories for the optional MSP multitenancy application."""

from __future__ import annotations

from typing import Any

import factory

from micboard.multitenancy.models import Campus, Organization, OrganizationMembership

from .base import ProjectModelFactory
from .registry import register_factory


@register_factory("micboard_multitenancy.Organization")
class OrganizationFactory(ProjectModelFactory):
    """Create a uniquely named tenant organization."""

    class Meta:
        model = Organization

    name = factory.Sequence(lambda number: f"Organization {number}")
    slug = factory.Sequence(lambda number: f"organization-{number}")


@register_factory("micboard_multitenancy.Campus")
class CampusFactory(ProjectModelFactory):
    """Create a campus belonging to one organization."""

    class Meta:
        model = Campus

    organization = factory.SubFactory("tests.factories.multitenancy.OrganizationFactory")
    name = factory.Sequence(lambda number: f"Campus {number}")
    slug = factory.Sequence(lambda number: f"campus-{number}")


@register_factory("micboard_multitenancy.OrganizationMembership")
class OrganizationMembershipFactory(ProjectModelFactory):
    """Create a campus-scoped membership with a consistent organization."""

    class Meta:
        model = OrganizationMembership

    user = factory.SubFactory("tests.factories.base.UserFactory")
    organization = factory.SubFactory("tests.factories.multitenancy.OrganizationFactory")
    campus = factory.SubFactory(
        "tests.factories.multitenancy.CampusFactory",
        organization=factory.SelfAttribute("..organization"),
    )

    @classmethod
    def _generate(cls, strategy: str, params: dict[str, Any]) -> OrganizationMembership:
        """Derive the organization when callers provide an existing campus."""
        campus = params.get("campus")
        if campus is not None and "organization" not in params:
            params = {**params, "organization": campus.organization}
        return super()._generate(strategy, params)

    @classmethod
    def _adjust_kwargs(cls, **kwargs: Any) -> dict[str, Any]:
        """Reject memberships whose campus belongs to another organization."""
        campus = kwargs.get("campus")
        organization = kwargs.get("organization")
        if campus is not None and organization is not None and campus.organization != organization:
            raise ValueError("Membership campus must belong to its organization")
        return super()._adjust_kwargs(**kwargs)
