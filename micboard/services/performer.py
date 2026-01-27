"""Performer service for managing performer lifecycle operations.

Handles CRUD operations for performers and their metadata.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import QuerySet

from micboard.models import Performer

if TYPE_CHECKING:
    pass


class PerformerService:
    """Business logic for performer management."""

    @staticmethod
    def create_performer(
        *,
        name: str,
        title: str = "",
        role_description: str = "",
        email: str = "",
        phone: str = "",
        photo_file=None,
        notes: str = "",
    ) -> Performer:
        """Create a new performer.

        Args:
            name: Performer name.
            title: Role or title (e.g., "Lead Vocalist").
            role_description: Description of role.
            email: Contact email.
            phone: Contact phone.
            photo_file: Image file for photo.
            notes: Notes about performer.

        Returns:
            Created Performer.
        """
        if not name or not name.strip():
            raise ValueError("Performer name is required")

        performer = Performer.objects.create(
            name=name.strip(),
            title=title.strip(),
            role_description=role_description.strip(),
            email=email.strip(),
            phone=phone.strip(),
            notes=notes.strip(),
        )

        if photo_file:
            performer.photo = photo_file
            performer.save(update_fields=["photo"])

        return performer

    @staticmethod
    def update_performer(
        *,
        performer: Performer,
        name: str | None = None,
        title: str | None = None,
        role_description: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        photo_file=None,
        notes: str | None = None,
    ) -> Performer:
        """Update performer metadata.

        Args:
            performer: Performer to update.
            name: New name or None to skip.
            title: New title or None to skip.
            role_description: New role description or None to skip.
            email: New email or None to skip.
            phone: New phone or None to skip.
            photo_file: New photo file or None to skip.
            notes: New notes or None to skip.

        Returns:
            Updated Performer.
        """
        updated_fields: list[str] = []

        if name is not None and performer.name != name.strip():
            performer.name = name.strip()
            updated_fields.append("name")

        if title is not None and performer.title != title.strip():
            performer.title = title.strip()
            updated_fields.append("title")

        if role_description is not None and performer.role_description != role_description.strip():
            performer.role_description = role_description.strip()
            updated_fields.append("role_description")

        if email is not None and performer.email != email.strip():
            performer.email = email.strip()
            updated_fields.append("email")

        if phone is not None and performer.phone != phone.strip():
            performer.phone = phone.strip()
            updated_fields.append("phone")

        if notes is not None and performer.notes != notes.strip():
            performer.notes = notes.strip()
            updated_fields.append("notes")

        if photo_file is not None:
            performer.photo = photo_file
            updated_fields.append("photo")

        if updated_fields:
            performer.save(update_fields=updated_fields)

        return performer

    @staticmethod
    def delete_performer(*, performer: Performer) -> None:
        """Delete a performer and all related assignments.

        Args:
            performer: Performer to delete.
        """
        performer.delete()

    @staticmethod
    def get_performer_by_id(*, performer_id: int) -> Performer | None:
        """Get a performer by ID.

        Args:
            performer_id: Performer database ID.

        Returns:
            Performer or None if not found.
        """
        return Performer.objects.filter(id=performer_id).first()

    @staticmethod
    def get_performer_by_name(*, name: str) -> Performer | None:
        """Get a performer by name (case-insensitive).

        Args:
            name: Performer name to search.

        Returns:
            Performer or None if not found.
        """
        return Performer.objects.filter(name__iexact=name).first()

    @staticmethod
    def get_all_performers(*, active_only: bool = True) -> QuerySet[Performer]:
        """Get all performers.

        Args:
            active_only: If True, only return active performers.

        Returns:
            QuerySet of Performer objects.
        """
        qs = Performer.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
        return qs.order_by("name")

    @staticmethod
    def search_performers(*, query: str, active_only: bool = True) -> list[Performer]:
        """Search performers by name or title.

        Args:
            query: Search string.
            active_only: If True, only search active performers.

        Returns:
            List of matching performers.
        """
        from django.db.models import Q

        qs = Performer.objects.filter(Q(name__icontains=query) | Q(title__icontains=query))

        if active_only:
            qs = qs.filter(is_active=True)

        return list(qs.order_by("name"))

    @staticmethod
    def deactivate_performer(*, performer: Performer) -> Performer:
        """Deactivate a performer (soft delete).

        Args:
            performer: Performer to deactivate.

        Returns:
            Updated performer.
        """
        performer.is_active = False
        performer.save(update_fields=["is_active"])
        return performer

    @staticmethod
    def reactivate_performer(*, performer: Performer) -> Performer:
        """Reactivate a deactivated performer.

        Args:
            performer: Performer to reactivate.

        Returns:
            Updated performer.
        """
        performer.is_active = True
        performer.save(update_fields=["is_active"])
        return performer

    @staticmethod
    def count_total_performers(*, active_only: bool = True) -> int:
        """Count total performers.

        Args:
            active_only: If True, count only active performers.

        Returns:
            Total count.
        """
        qs = Performer.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
        return qs.count()

    @staticmethod
    def get_performers_with_assignments(*, active_only: bool = True) -> QuerySet[Performer]:
        """Get performers that have active assignments.

        Args:
            active_only: If True, only return active performers.

        Returns:
            QuerySet of performers with assignments.
        """
        qs = Performer.objects.filter(assignments__is_active=True).distinct()

        if active_only:
            qs = qs.filter(is_active=True)

        return qs.order_by("name")
