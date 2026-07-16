<aside>
💡 Try to be concise with answers
Each project submission has to be reduced to around 400 words
</aside>

# SRED Project Summary — 2026 Introduce DRF API Layer (v1 Read-Only)

## Project Description

django-micboard has no REST API. All user interaction goes through Django admin views (Django templates + HTMX). This means: no programmatic access for external integrations (third-party tools, mobile apps, automation); no documented API contract — all data access is admin-only; no serialization layer — form classes in `micboard/forms/settings.py` (297 lines) serve as the closest equivalent but are tightly coupled to template rendering. The lack of versioning means API-breaking changes cannot be communicated or migrated gracefully.

## Project Goals

Introduce Django REST Framework (DRF) as the API framework. Create `micboard/api/v1/` with submodules mirroring domain structure: serializers (hardware, discovery, monitoring, settings), views (ViewSets for chassis, units, channels, discovery, monitoring, settings), permissions, filters, pagination. API v1 is read-only initially — expose GET endpoints for hardware inventory, discovery status, monitoring state, and settings. This avoids write-side validation and conflict resolution upfront. Future versions (v2+) get new `micboard/api/v2/` namespaces without breaking v1 consumers. Admin views remain the primary UI. Serializer classes replace the need for form classes over time.

## Technical Uncertainties

### Uncertainty #1: Read-Only API Over Domain Logic Without Duplication

**Description:** The domain logic lives in services (`micboard/services/`). An API layer must not duplicate business rules (validation, filtering, tenant scoping). The uncertainty: how to reuse service-layer query logic in DRF views without coupling serializers to service internals.

**Experiments (Planned):**
- Spike: service methods return querysets with tenant scoping applied; views use `get_queryset()` delegating to service; serializers only shape output
- Alternative: service methods return DTO lists; views serialize DTOs directly — simpler but loses queryset optimization (pagination, filtering)

**Results / Learnings / Success:**
- (To be determined during implementation)

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-007 Introduce DRF API Layer with Versioning](../../adr/007-api-layer-introduction.md)

### Uncertainty #2: Versioning Strategy Without Admin Coupling

**Description:** Admin views use HTMX fragments with implicit contracts (context variable names, template structure). API serializers must be independent but semantically equivalent. The uncertainty: how to evolve API without forcing admin changes or vice versa.

**Experiments (Planned):**
- Separate serializer modules per version; shared field definitions in `api/common/fields.py`
- API version negotiated via URL path (`/api/v1/`, `/api/v2/`) not header
- Admin templates continue using form classes; serializers only for API

**Results / Learnings / Success:**
- (To be determined during implementation)

**Uncertainty-Specific Documentation & Links:**
- **ADR:** [ADR-007 Introduce DRF API Layer with Versioning](../../adr/007-api-layer-introduction.md)

---

## Participants

| Name | Role | % Yearly Time | Contribution |
|------|------|---------------|--------------|
| (team lead) | Architecture / ADR | ~15% | ADR-007, versioning strategy |
| (engineer) | Serializers / Views | ~40% | Domain serializers, ViewSets, permissions |
| (engineer) | Testing / Documentation | ~25% | Schema generation, browsable API, contract tests |

---

## Project Documentation & Links

**Project Docs:**
- [ADR-007 Introduce DRF API Layer with Versioning](../../adr/007-api-layer-introduction.md)

**PRs:**
- (DRF dependency + v1 skeleton PR)
- (hardware serializers + views PR)
- (discovery/monitoring serializers + views PR)
- (settings serializers + views PR)
- (permissions + pagination + filtering PR)