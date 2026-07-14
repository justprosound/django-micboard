from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from micboard.models.users.user_profile import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Micboard Profile"


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "get_user_type",
    )

    @admin.display(description="Role")
    def get_user_type(self, obj: User) -> str:
        return obj.profile.get_user_type_display() if hasattr(obj, "profile") else "-"


def configure_user_admin(site: admin.AdminSite) -> None:
    """Enhance an existing User admin without overriding host registration policy."""
    if not site.is_registered(User):
        return

    site.unregister(User)
    site.register(User, UserAdmin)


configure_user_admin(admin.site)
