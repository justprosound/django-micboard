"""Shared pytest configuration and fixtures for django-micboard tests.

This module provides:
- Shared fixtures for common test patterns
- User factory fixtures (admin, regular, staff users)
- Authenticated client fixtures
- Django site fixtures for multi-site testing

The database and Django setup are handled automatically by pytest-django
and the configuration in tests/settings.py and pyproject.toml.
"""

# Bootstrapping django.core.checks to avoid circular import issues on Python 3.13 / Django 5.1
try:
    import sys

    import django
    import django.core

    if "django.core.checks" not in sys.modules:
        from types import ModuleType

        checks = ModuleType("django.core.checks")
        checks.__path__ = [django.core.__path__[0] + "/checks"]
        sys.modules["django.core.checks"] = checks
        django.core.checks = checks

        import django.core.checks.messages
        import django.core.checks.registry

        checks.Error = django.core.checks.messages.Error
        checks.Warning = django.core.checks.messages.Warning
        checks.Tags = django.core.checks.registry.Tags
        checks.register = django.core.checks.registry.register

        import django.core.checks.async_checks
        import django.core.checks.caches
        import django.core.checks.database
        import django.core.checks.files
        import django.core.checks.model_checks
        import django.core.checks.security.base
        import django.core.checks.security.csrf
        import django.core.checks.security.sessions
        import django.core.checks.templates
        import django.core.checks.translation

        for name in [
            "CheckMessage",
            "Critical",
            "Debug",
            "Error",
            "Info",
            "Warning",
            "CRITICAL",
            "DEBUG",
            "ERROR",
            "INFO",
            "WARNING",
            "run_checks",
            "tag_exists",
        ]:
            setattr(checks, name, locals()[name])
except Exception:  # noqa: S110
    pass

import pytest

ADMIN_PASSWORD = "admin123"
REGULAR_PASSWORD = "testpass123"
STAFF_PASSWORD = "staffpass123"


@pytest.fixture
def admin_user(db, django_user_model):
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
    user = django_user_model.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password=ADMIN_PASSWORD,
    )
    return user


@pytest.fixture
def regular_user(db, django_user_model):
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
    user = django_user_model.objects.create_user(
        username="testuser",
        email="user@example.com",
        password=REGULAR_PASSWORD,
    )
    return user


@pytest.fixture
def staff_user(db, django_user_model):
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
    user = django_user_model.objects.create_user(
        username="staff",
        email="staff@example.com",
        password=STAFF_PASSWORD,
        is_staff=True,
    )
    return user


@pytest.fixture
def django_client():
    """Provide a Django test client for making HTTP requests.

    Returns:
        Client: Django test client instance for making requests in tests.
    """
    from django.test import Client

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
    django_client.force_login(regular_user)
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
    django_client.force_login(admin_user)
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
    from django.contrib.sites.models import Site

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
