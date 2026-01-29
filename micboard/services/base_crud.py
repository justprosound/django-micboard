"""Generic CRUD service base class to reduce duplication across service classes.

Provides common patterns for Create, Read, Update, Delete operations with
logging and audit support.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Generic, TypeVar

from django.db.models import QuerySet

if TYPE_CHECKING:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)

# Generic type for model instances
T = TypeVar("T")


class GenericCRUDService(Generic[T]):
    """Base CRUD service providing common operations with minimal duplication.

    Subclasses should define:
    - model_class: The Django model class to operate on
    - filterable_fields: Dict of query param names to model field names
    """

    model_class: type[T] = None  # type: ignore

    @classmethod
    def get_all(cls) -> QuerySet[T]:
        """Get all objects of this type.

        Returns:
            QuerySet of all objects.
        """
        if cls.model_class is None:
            raise NotImplementedError("Subclass must define model_class")
        return cls.model_class.objects.all()

    @classmethod
    def get_active(cls, **filters) -> QuerySet[T]:
        """Get all active objects (is_active=True by default).

        Args:
            **filters: Additional filters to apply.

        Returns:
            QuerySet of active objects.
        """
        qs = cls.model_class.objects.filter(is_active=True, **filters)

        # Apply ordering if model has name field
        try:
            qs = qs.order_by("name")
        except Exception:
            pass

        return qs

    @classmethod
    def get_page(cls, page: int = 1, page_size: int = 50, **filters) -> QuerySet[T]:
        """Get paginated results.

        Args:
            page: Page number (1-indexed).
            page_size: Results per page.
            **filters: Additional filters.

        Returns:
            QuerySet sliced to page.
        """
        qs = cls.model_class.objects.filter(**filters)
        offset = (page - 1) * page_size
        return qs[offset : offset + page_size]

    @classmethod
    def count(cls, **filters) -> int:
        """Count objects matching filters.

        Args:
            **filters: Filters to apply.

        Returns:
            Count of matching objects.
        """
        return cls.model_class.objects.filter(**filters).count()

    @classmethod
    def get_by_id(cls, obj_id: int) -> T | None:
        """Get single object by ID.

        Args:
            obj_id: Primary key.

        Returns:
            Model instance or None.
        """
        try:
            return cls.model_class.objects.get(id=obj_id)
        except cls.model_class.DoesNotExist:
            return None

    @classmethod
    def deactivate(cls, obj_id: int, user: object | None = None) -> bool:
        """Deactivate an object (soft delete via is_active flag).

        Args:
            obj_id: Primary key to deactivate.
            user: User performing action (for audit).

        Returns:
            True if successful, False otherwise.
        """
        try:
            obj = cls.model_class.objects.get(id=obj_id)
            obj.is_active = False

            # Try to set updated_by if model has it
            if hasattr(obj, "updated_by") and user:
                obj.updated_by = user

            obj.save(update_fields=["is_active", "updated_at"])
            logger.info(f"Deactivated {cls.model_class.__name__} {obj_id}")
            return True
        except cls.model_class.DoesNotExist:
            logger.warning(f"{cls.model_class.__name__} {obj_id} not found")
            return False
        except Exception as e:
            logger.error(f"Failed to deactivate {cls.model_class.__name__} {obj_id}: {e}")
            return False

    @classmethod
    def activate(cls, obj_id: int) -> bool:
        """Reactivate a deactivated object.

        Args:
            obj_id: Primary key to activate.

        Returns:
            True if successful, False otherwise.
        """
        try:
            obj = cls.model_class.objects.get(id=obj_id)
            obj.is_active = True
            obj.save(update_fields=["is_active", "updated_at"])
            logger.info(f"Activated {cls.model_class.__name__} {obj_id}")
            return True
        except cls.model_class.DoesNotExist:
            return False

    @classmethod
    def delete_permanently(cls, obj_id: int) -> bool:
        """Permanently delete an object.

        Args:
            obj_id: Primary key to delete.

        Returns:
            True if successful, False otherwise.
        """
        try:
            obj = cls.model_class.objects.get(id=obj_id)
            obj.delete()
            logger.info(f"Permanently deleted {cls.model_class.__name__} {obj_id}")
            return True
        except cls.model_class.DoesNotExist:
            return False

    @classmethod
    def exists(cls, **filters) -> bool:
        """Check if object matching filters exists.

        Args:
            **filters: Filters to check.

        Returns:
            True if exists, False otherwise.
        """
        return cls.model_class.objects.filter(**filters).exists()

    @classmethod
    def search(cls, query: str, search_fields: list[str] | None = None) -> QuerySet[T]:
        """Search objects by query string across specified fields.

        Args:
            query: Search query string.
            search_fields: Fields to search in. If None, searches 'name' and 'description'.

        Returns:
            QuerySet of matching objects.
        """
        from django.db.models import Q

        if search_fields is None:
            search_fields = ["name", "description"]

        q_objects = Q()
        for field in search_fields:
            q_objects |= Q(**{f"{field}__icontains": query})

        return cls.model_class.objects.filter(q_objects)
