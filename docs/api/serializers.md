# Serializers

django-micboard does not currently expose a stable public REST serializer package. A versioned,
tenant-safe REST API is tracked in
[GitHub issue #74](https://github.com/justprosound/django-micboard/issues/74).

Internal service boundaries use Pydantic v2 DTOs under domain service packages. Host projects
building an API should define their own DRF serializers over tenant-scoped service results, and
must not serialize an unscoped model queryset directly.

See [HTTP endpoints](endpoints.md) for the current public surface.
