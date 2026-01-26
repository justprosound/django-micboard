# Django Micboard - Refactor & Release Plan

## Executive Summary
Comprehensive refactoring plan to improve code quality, test coverage (target: 95%), architecture robustness, and prepare for CalVer release.

## Phase Overview

### Phase 1: Audit & Analysis (Current)
- [x] Identify monolithic files and repeated logic
- [x] Map signal usage and DRY violations
- [ ] Generate test coverage baseline
- [ ] Document architecture gaps

### Phase 2: Test Infrastructure Enhancement
- [ ] Expand unit test suite (target: 95% coverage)
- [ ] Implement integration tests
- [ ] Add end-to-end scenarios
- [ ] Edge case validation

### Phase 3: Refactoring & DRY Improvements
- [ ] Extract services layer (reduce signals)
- [ ] Modularize common logic
- [ ] Improve plugin architecture
- [ ] Enhance admin/developer experience

### Phase 4: Code Quality & CI/CD
- [ ] Run pre-commit linting (uvx)
- [ ] Update coverage reporting
- [ ] Enhance GitHub Actions workflows
- [ ] Release documentation

### Phase 5: Release Preparation (CalVer)
- [ ] Version bumping: YY.MM.DD format
- [ ] Changelog generation
- [ ] PyPI packaging standards
- [ ] Django app registration

## Key Recommendations

### Architecture Improvements
1. **Services Layer**: Move business logic from signals → service classes
2. **Plugin Registry**: Simplify manufacturer plugin discovery
3. **Polling Strategy**: Improve poll_devices command resilience
4. **Error Handling**: Centralized exception handling and logging

### DRY Principle Applications
1. Consolidate serializer logic
2. Extract common permissions patterns
3. Unify rate-limiting decorators
4. Reduce model manager duplication

### Test Strategy
- Unit: 85% target (isolated components)
- Integration: 10% target (plugin + model interactions)
- E2E: 5% target (full workflows)

### Minimal Dependencies
- Keep core requirements light
- Optional: Django-Q (tasks), Channels (WS)
- Avoid unnecessary vendoring

## Timeline & Success Metrics
- Coverage: Current → 95% target
- Code Quality: 0 linting errors (pre-commit)
- Release: CalVer 25.01.DD (January release)
- CI/CD: Green builds on all PRs
