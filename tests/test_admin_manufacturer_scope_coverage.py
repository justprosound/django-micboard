"""Coverage for manufacturer workflows and tenant-aware admin scoping."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, override_settings

from micboard.admin import manufacturers, mixins, sortable
from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.discovery.manufacturer import Manufacturer


def _request(method: str = "get", data: dict[str, Any] | None = None) -> Any:
    request = getattr(RequestFactory(), method)("/admin/", data or {})
    request.user = SimpleNamespace(
        pk=4,
        is_authenticated=True,
        is_superuser=True,
        is_staff=True,
        has_perm=Mock(return_value=True),
    )
    return request


def _admin(admin_class: type, model: type) -> Any:
    return admin_class(model, AdminSite())


def test_manufacturer_form_discovers_plugins_redacts_and_restores_config() -> None:
    instance = Manufacturer(pk=1, code="vendor", config={"token": "secret"})
    modules = [(None, "good", False), (None, "broken", False)]

    def get_plugin(name: str) -> object:
        if name == "broken":
            raise RuntimeError("unavailable")
        return object()

    with (
        patch.object(manufacturers.pkgutil, "iter_modules", return_value=modules),
        patch.object(manufacturers, "get_manufacturer_plugin", side_effect=get_plugin),
        patch.object(manufacturers, "redact_secrets", return_value={"token": "***"}),
    ):
        form = manufacturers.ManufacturerAdminForm(instance=instance)
    assert form.initial["config"] == {"token": "***"}
    assert list(form.fields["code"].widget.choices) == [("good", "Good")]
    assert "auto-discovered" in form.fields["code"].help_text
    form.cleaned_data = {"config": {"token": "***"}}
    with patch.object(
        manufacturers, "restore_redacted_secrets", return_value=instance.config
    ) as restore:
        assert form.clean_config() == instance.config
    restore.assert_called_once_with({"token": "***"}, instance.config)


def test_manufacturer_form_survives_registry_scan_failure_and_new_blank_config() -> None:
    with patch.object(
        manufacturers.pkgutil, "iter_modules", side_effect=RuntimeError("scan failure")
    ):
        form = manufacturers.ManufacturerAdminForm(instance=Manufacturer())
    assert not isinstance(form.fields["code"].widget, manufacturers.forms.Select)
    form.cleaned_data = {"config": None}
    with patch.object(manufacturers, "restore_redacted_secrets", return_value={}):
        assert form.clean_config() == {}


def test_manufacturer_admin_links_secure_fieldsets_and_urls() -> None:
    model_admin = _admin(manufacturers.ManufacturerAdmin, Manufacturer)
    request = _request()
    assert "Save the manufacturer" in model_admin.settings_link(SimpleNamespace(pk=None))
    with patch.object(manufacturers, "reverse", return_value="/settings/"):
        assert "manufacturer=5" in model_admin.settings_link(SimpleNamespace(pk=5))
    obj = SimpleNamespace(config={"token": "secret"})
    with (
        patch.object(model_admin, "has_change_permission", return_value=False),
        patch.object(manufacturers, "replace_field", return_value=[("safe", {})]),
    ):
        assert model_admin.get_fieldsets(request, obj) == [("safe", {})]
    with patch.object(MicboardModelAdmin, "get_fieldsets", return_value=[("base", {})]):
        assert model_admin.get_fieldsets(request, None) == [("base", {})]
    with patch.object(manufacturers, "redact_secrets", return_value={"token": "***"}):
        assert '"***"' in model_admin.config_redacted(obj)


class _FilterHost(mixins.EnhancedAdminMixin):
    def _base_filters(self) -> list[Any]:
        return ["created_at", "date", "status", object()]

    def get_list_filter(self, request: Any) -> list[Any]:
        return mixins.EnhancedAdminMixin.get_list_filter(self, request)


def test_enhanced_admin_filters_plain_unfold_and_rangefilter_modes() -> None:
    host = _FilterHost()
    parent = type("Parent", (), {"get_list_filter": lambda self, request: host._base_filters()})
    dynamic = type("DynamicFilterHost", (mixins.EnhancedAdminMixin, parent), {})()
    with (
        patch.object(mixins, "HAS_UNFOLD_FILTERS", False),
        patch.object(mixins, "HAS_RANGE_FILTER", False),
    ):
        plain = dynamic.get_list_filter(_request())
    assert plain[:3] == ["created_at", "date", "status"]

    with (
        patch.object(mixins, "HAS_UNFOLD_FILTERS", True),
        patch.object(mixins, "RangeDateTimeFilter", "datetime"),
        patch.object(mixins, "RangeDateFilter", "date-range"),
    ):
        unfolded = dynamic.get_list_filter(_request())
    assert unfolded[:3] == [("created_at", "datetime"), ("date", "date-range"), "status"]

    rangefilter_module = SimpleNamespace(
        DateRangeFilter="date-range", DateTimeRangeFilter="datetime-range"
    )
    with (
        patch.object(mixins, "HAS_UNFOLD_FILTERS", False),
        patch.object(mixins, "HAS_RANGE_FILTER", True),
        patch.dict("sys.modules", {"rangefilter.filters": rangefilter_module}),
    ):
        ranged = dynamic.get_list_filter(_request())
    assert ranged[:3] == [
        ("created_at", "datetime-range"),
        ("date", "date-range"),
        "status",
    ]


def _queryset(label: str = "micboard.location") -> MagicMock:
    queryset = MagicMock()
    queryset.model._meta.label_lower = label
    queryset.model.objects = MagicMock()
    queryset.model._default_manager = MagicMock()
    queryset.db = "default"
    return queryset


@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=False)
def test_admin_scope_is_noop_when_tenant_modes_disabled() -> None:
    queryset = _queryset()
    assert MicboardModelAdmin._scope_queryset_for_user(queryset, user=_request().user) is queryset


@override_settings(
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_MULTI_SITE_MODE=False,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=True,
)
def test_admin_scope_allows_cross_org_superuser() -> None:
    queryset = _queryset()
    assert MicboardModelAdmin._scope_queryset_for_user(queryset, user=_request().user) is queryset


@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True)
def test_admin_scope_allows_reviewed_platform_global_superuser() -> None:
    queryset = _queryset("micboard.activitylog")
    assert MicboardModelAdmin._scope_queryset_for_user(queryset, user=_request().user) is queryset


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_MULTI_SITE_MODE=True)
def test_admin_scope_intersects_manager_visibility_using_same_database() -> None:
    queryset = _queryset()
    visible = MagicMock()
    queryset.model.objects.for_user.return_value = visible
    result = MicboardModelAdmin._scope_queryset_for_user(queryset, user=_request().user)
    assert result is queryset.filter.return_value
    visible.using.assert_called_once_with("default")
    queryset.filter.assert_called_once_with(pk__in=visible.using.return_value.values.return_value)


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_MULTI_SITE_MODE=True)
def test_admin_scope_falls_back_to_tenant_queryset_contract() -> None:
    queryset = _queryset()
    queryset.model.objects = SimpleNamespace()
    tenant_queryset = MagicMock()
    with patch(
        "micboard.models.base_managers.TenantOptimizedQuerySet", return_value=tenant_queryset
    ) as constructor:
        MicboardModelAdmin._scope_queryset_for_user(queryset, user=_request().user)
    constructor.assert_called_once_with(queryset.model, using="default")
    tenant_queryset.for_user.assert_called_once()


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_MULTI_SITE_MODE=True)
def test_related_queryset_scope_skips_shared_and_builds_database_manager_queryset() -> None:
    model_admin = _admin(MicboardModelAdmin, Manufacturer)
    request = _request()
    shared = SimpleNamespace(
        remote_field=SimpleNamespace(
            model=SimpleNamespace(_meta=SimpleNamespace(label_lower="micboard.manufacturer"))
        )
    )
    kwargs: dict[str, Any] = {}
    model_admin._scope_related_queryset(shared, request, kwargs)
    assert kwargs == {}

    manager = MagicMock()
    related_model = SimpleNamespace(
        _meta=SimpleNamespace(label_lower="micboard.location"),
        _default_manager=manager,
    )
    db_field = SimpleNamespace(remote_field=SimpleNamespace(model=related_model))
    with (
        patch.object(model_admin, "_scope_queryset_for_user", return_value="scoped") as scope,
        patch.object(
            mixins.tenant_role_access,
            "scope_manageable_queryset",
            return_value="managed",
        ) as manage,
    ):
        kwargs = {"using": "replica"}
        model_admin._scope_related_queryset(db_field, request, kwargs)
    manager.db_manager.assert_called_once_with("replica")
    assert kwargs["queryset"] == "managed"
    scope.assert_called_once_with(
        manager.db_manager.return_value.all.return_value, user=request.user
    )
    manage.assert_called_once_with("scoped", user=request.user)

    supplied = object()
    with (
        patch.object(model_admin, "_scope_queryset_for_user", return_value="supplied-scoped"),
        patch.object(
            mixins.tenant_role_access,
            "scope_manageable_queryset",
            return_value="supplied-managed",
        ),
    ):
        kwargs = {"queryset": supplied}
        model_admin._scope_related_queryset(db_field, request, kwargs)
    assert kwargs["queryset"] == "supplied-managed"


@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=False)
def test_related_queryset_scope_is_noop_without_tenant_modes() -> None:
    model_admin = _admin(MicboardModelAdmin, Manufacturer)
    kwargs: dict[str, Any] = {}
    model_admin._scope_related_queryset(SimpleNamespace(), _request(), kwargs)
    assert kwargs == {}


def test_admin_queryset_and_relationship_widget_methods_delegate_scoped_querysets() -> None:
    model_admin = _admin(MicboardModelAdmin, Manufacturer)
    request = _request()
    queryset = MagicMock()
    with (
        patch.object(mixins.BaseAdmin, "get_queryset", return_value=queryset),
        patch.object(model_admin, "_scope_queryset_for_user", return_value="scoped") as scope,
    ):
        assert model_admin.get_queryset(request) == "scoped"
    scope.assert_called_once_with(queryset, user=request.user)

    field = MagicMock()
    with (
        patch.object(model_admin, "_scope_related_queryset") as scope_related,
        patch.object(mixins.BaseAdmin, "formfield_for_foreignkey", return_value="fk"),
        patch.object(mixins.BaseAdmin, "formfield_for_manytomany", return_value="m2m"),
    ):
        assert model_admin.formfield_for_foreignkey(field, request, using="replica") == "fk"
        assert model_admin.formfield_for_manytomany(field, request, using="replica") == "m2m"
    assert scope_related.call_count == 2


def test_sortable_admin_template_property_uses_base_and_explicit_override() -> None:
    model_admin = _admin(sortable.MicboardSortableAdmin, Manufacturer)
    with patch.object(
        sortable.BaseSortableAdmin,
        "change_list_template",
        "base-template",
        create=True,
    ):
        assert model_admin.change_list_template == "base-template"
    model_admin.change_list_template = "custom-template"
    assert model_admin.change_list_template == "custom-template"
