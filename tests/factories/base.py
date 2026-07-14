"""Shared factory primitives for test-only model graphs."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.sites.models import Site

import factory
from factory.django import DjangoModelFactory


class ProjectModelFactory(DjangoModelFactory):
    """Base for project factories with deterministic post-generation persistence."""

    class Meta:
        abstract = True
        skip_postgeneration_save = True


class UserFactory(ProjectModelFactory):
    """Create users through the host project's configured user model."""

    class Meta:
        model = settings.AUTH_USER_MODEL

    username = factory.Sequence(lambda number: f"user-{number}")
    email = factory.LazyAttribute(lambda user: f"{user.username}@example.test")
    password = factory.LazyFunction(lambda: make_password("factory-password"))


class SiteFactory(ProjectModelFactory):
    """Create unique Django sites for project-model relationships."""

    class Meta:
        model = Site

    domain = factory.Sequence(lambda number: f"site-{number}.example.test")
    name = factory.LazyAttribute(lambda site: site.domain)
