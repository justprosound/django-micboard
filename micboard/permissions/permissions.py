"""REST permissions used across Micboard views and APIs."""

from rest_framework import permissions


class IsStaffOrReadOnly(permissions.BasePermission):
    """Custom permission to only allow staff users to edit objects, and all users to read."""

    def has_permission(self, request, view):
        """Grant access if request is safe or user is staff."""
        # Read permissions are allowed to any request, so we'll always allow
        # GET, HEAD, or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to staff users.
        return request.user and request.user.is_staff


class IsGroupMemberOrReadOnly(permissions.BasePermission):
    """Custom permission for membership-restricted writes.

    Only users in the object's associated group may modify it; reads are open to all. Objects are
    expected to expose a `group` attribute or equivalent relationship.
    """

    def has_object_permission(self, request, view, obj):
        """Allow reads for everyone and writes only to group members."""
        # Read permissions are allowed to any request.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to members of the associated group.
        # This assumes the object has a 'group' attribute or a method to get the associated group.
        if hasattr(obj, "group") and request.user in obj.group.user_set.all():
            return True

        # Fallback for objects that might not have a direct 'group' attribute, but are related
        # For example, if a Receiver is assigned to a Location, and Location has a group.
        # This part would need more specific implementation based on the data model.
        # For now, we'll keep it simple and assume a direct 'group' attribute.

        return False
