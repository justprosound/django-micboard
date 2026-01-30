# Tasks

## Phase 2 - Refactor (Code & Packaging)

- [ ] Align services with tenant-aware QuerySet helpers to remove duplicated filtering logic.
- [ ] Implement admin settings overrides diff view and wire URL to real view.
- [ ] Ensure settings registry usage is consistent for configuration lookups.
- [ ] Verify plugin registry usage for manufacturer-agnostic behavior.

## Phase 3 - Tests

- [ ] Add/extend tests for settings registry resolution order and required settings.
- [ ] Add/extend tests for tenant scoping behavior in services.
- [ ] Add/extend tests for settings diff admin view access and output.

## Phase 4 - Docs/Tooling

- [ ] Update README with integration and release prep notes.
- [ ] Update CONTRIBUTING with migration safety and workflow notes.
- [ ] Update CHANGELOG for refactor entries.
- [ ] Ensure `.gitignore`, pre-commit, and ruff configs are complete.
