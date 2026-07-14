"""Factory catalog for installed django-micboard models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module

from django.apps import apps
from django.db import models

from factory.django import DjangoModelFactory

type FactoryClass = type[DjangoModelFactory]

_CORE_FACTORY_MODULES = (
    "tests.factories.audit",
    "tests.factories.discovery",
    "tests.factories.hardware",
    "tests.factories.locations",
    "tests.factories.monitoring",
    "tests.factories.realtime",
    "tests.factories.rf_coordination",
    "tests.factories.settings",
    "tests.factories.telemetry",
    "tests.factories.users",
)
_OPTIONAL_FACTORY_MODULES = {
    "micboard.multitenancy": "tests.factories.multitenancy",
}


@dataclass(frozen=True, slots=True)
class FactorySpec:
    """One registered model label and its concrete factory."""

    label: str
    factory: FactoryClass


_factory_specs: dict[str, FactorySpec] = {}


def register_factory(label: str) -> Callable[[FactoryClass], FactoryClass]:
    """Register a concrete factory for a project model label."""
    normalized_label = label.lower()

    def decorator(factory_class: FactoryClass) -> FactoryClass:
        if normalized_label in _factory_specs:
            raise RuntimeError(f"Duplicate factory registration for {label}")
        _factory_specs[normalized_label] = FactorySpec(label=label, factory=factory_class)
        return factory_class

    return decorator


def _load_factories() -> None:
    """Import the installed domain adapters through Python's module cache."""
    for module_name in _CORE_FACTORY_MODULES:
        import_module(module_name)
    for app_name, module_name in _OPTIONAL_FACTORY_MODULES.items():
        if apps.is_installed(app_name):
            import_module(module_name)


def _model_label(model_or_label: type[models.Model] | models.Model | str) -> str:
    """Normalize a model class, instance, or label for catalog lookup."""
    if isinstance(model_or_label, str):
        return model_or_label.lower()
    return model_or_label._meta.label_lower


def factory_for(model_or_label: type[models.Model] | models.Model | str) -> FactoryClass:
    """Return the registered factory for a model class, instance, or label."""
    _load_factories()
    label = _model_label(model_or_label)
    try:
        return _factory_specs[label].factory
    except KeyError as exc:
        raise LookupError(f"No factory registered for {label}") from exc


def iter_factory_specs() -> tuple[FactorySpec, ...]:
    """Return installed factory registrations in stable label order."""
    _load_factories()
    return tuple(sorted(_factory_specs.values(), key=lambda spec: spec.label.lower()))
