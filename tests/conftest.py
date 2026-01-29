"""Shared pytest configuration and fixtures for django-micboard tests.

This module provides:
- Shared fixtures for common test patterns
- User factory fixtures (admin, regular, staff users)
- Authenticated client fixtures
- Django site fixtures for multi-site testing

The database and Django setup are handled automatically by pytest-django
and the configuration in tests/settings.py and pyproject.toml.
"""

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.test import Client

import pytest


@pytest.fixture
def admin_user(db):
    """Create a superuser for testing admin functionality.

    Provides a superuser with credentials:
    - username: admin
    - password: admin123
    - email: admin@example.com

    Args:
        db: pytest-django fixture for database access

    Returns:
        User: The created superuser instance
    """
    user = User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin123",
    )
    return user


@pytest.fixture
def regular_user(db):
    """Create a regular user for testing non-admin functionality.

    Provides a standard user with credentials:
    - username: testuser
    - password: testpass123
    - email: user@example.com

    Args:
        db: pytest-django fixture for database access

    Returns:
        User: The created regular user instance
    """
    user = User.objects.create_user(
        username="testuser",
        email="user@example.com",
        password="testpass123",
    )
    return user


@pytest.fixture
def staff_user(db):
    """Create a staff user (but not superuser) for testing.

    Provides a staff user with credentials:
    - username: staff
    - password: staffpass123
    - email: staff@example.com

    Args:
        db: pytest-django fixture for database access

    Returns:
        User: The created staff user instance
    """
    user = User.objects.create_user(
        username="staff",
        email="staff@example.com",
        password="staffpass123",
        is_staff=True,
    )
    return user


@pytest.fixture
def django_client():
    """Provide a Django test client for making HTTP requests.

    Returns:
        Client: Django test client instance for making requests in tests.
    """
    return Client()


@pytest.fixture
def authenticated_client(django_client, regular_user):
    """Provide a Django test client logged in as a regular user.

    Combines the test client with an authenticated user session.

    Args:
        django_client: Test client fixture
        regular_user: Regular user fixture

    Returns:
        Client: Django test client authenticated as regular_user.
    """
    django_client.login(username="testuser", password="testpass123")
    return django_client


@pytest.fixture
def admin_client(django_client, admin_user):
    """Provide a Django test client logged in as an admin user.

    Combines the test client with an authenticated admin session.

    Args:
        django_client: Test client fixture
        admin_user: Admin user fixture

    Returns:
        Client: Django test client authenticated as admin_user.
    """
    django_client.login(username="admin", password="admin123")
    return django_client


@pytest.fixture
def default_site(db):
    """Get or create the default Django site for testing.

    The default site has:
    - pk: 1
    - domain: example.com
    - name: example.com

    Args:
        db: pytest-django fixture for database access

    Returns:
        Site: The default site instance.
    """
    site, _ = Site.objects.get_or_create(
        pk=1,
        defaults={
            "domain": "example.com",
            "name": "example.com",
        },
    )
    return site


# pytest-django configuration hooks


def pytest_configure(config):
    """Configure pytest at startup.

    This hook is called after command line options have been parsed
    and before tests are collected. It's useful for setting up global
    test configuration.

    Args:
        config: pytest config object
    """
    # Database and Django setup is handled by pytest-django
    # and tests/settings.py configuration


def pytest_collection_modifyitems(config, items):
    """Modify test collection to apply markers automatically.

    This hook allows programmatic marker application based on test names
    or other criteria. Currently used for documentation only.

    Args:
        config: pytest config object
        items: list of collected test items
    """
    # Custom marker application logic can be added here if needed
    # For example: automatically mark integration tests as slow
    pass
