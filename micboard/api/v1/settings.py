from typing import Any
from rest_framework import permissions
from rest_framework.viewsets import ReadOnlyModelViewSet

from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.serializers.v1.settings import SettingDefinitionSerializer, SettingSerializer
from micboard.services.settings.visibility_service import settings_visibility


class SettingDefinitionViewSet(ReadOnlyModelViewSet):  # type: ignore[misc]
    """Read-only viewset for SettingDefinition."""

    serializer_class = SettingDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self) -> "Any":
        return SettingDefinition.objects.filter(is_active=True)


class SettingViewSet(ReadOnlyModelViewSet):  # type: ignore[misc]
    """Read-only viewset for Setting overrides."""

    serializer_class = SettingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self) -> "Any":
        user = self.request.user
        if not user.is_authenticated:
            return Setting.objects.none()

        scope = settings_visibility.for_user(user=user)
        q_filter = settings_visibility.build_filter(scope)
        return Setting.objects.filter(q_filter)
