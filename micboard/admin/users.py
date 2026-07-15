from django.contrib import admin

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.users.user_profile import UserProfile


class UserProfileAdmin(MicboardModelAdmin):
    """Administer Micboard profile data without replacing the host's User admin."""

    list_display = ("user", "user_type", "title", "last_active_at", "updated_at")
    list_filter = ("user_type", "last_active_at")
    search_fields = ("user__username", "user__email", "title")
    list_select_related = ("user",)
    readonly_fields = ("created_at", "updated_at", "last_active_at")
    raw_id_fields = ("user",)


def register_user_profile_admin(site: admin.AdminSite) -> None:
    """Register Micboard's profile on a site without mutating host User policy."""
    if site.is_registered(UserProfile):
        return

    site.register(UserProfile, UserProfileAdmin)


register_user_profile_admin(admin.site)
