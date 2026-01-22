# Documentation Refactoring Plan

## Current Issues
- Duplicate files: `configuration.md` + `CONFIGURATION.md`, `services.md` + multiple service docs
- Outdated files: Some docs reference old architecture 
- Inconsistent structure: Some files very long (500+ lines), others short
- Mixed purposes: Some docs combine setup + reference + troubleshooting

## Proposed Structure

### Core Documentation (Essentials)
```
docs/
├── index.md                          # Main index & quick links
├── quickstart.md                     # 5-min setup
├── configuration.md                  # All config options (consolidated)
└── SHURE_NETWORK_GUID_TROUBLESHOOTING.md  # Critical GUID issue guide
```

### Setup & Development
```
development/
├── setup.md                          # Development environment setup
├── testing.md                        # Testing guide (unit + integration)
└── debugging.md                      # Debugging tips
```

### API & Integration
```
api/
├── endpoints.md                      # REST API endpoints (Shure-specific)
├── models.md                         # Data models explanation
├── websocket.md                      # WebSocket real-time updates
└── serializers.md                    # Data serialization
```

### Architecture & Advanced
```
advanced/
├── architecture.md                   # System design (high-level)
├── plugin-development.md             # Create manufacturer plugins
├── rate-limiting.md                  # Rate limiting explained
└── user-assignments.md               # User assignment system
```

### Operations & Monitoring
```
operations/
├── polling.md                        # Device polling service
├── monitoring.md                     # Live monitoring & dashboards
└── alerts.md                         # Alert configuration
```

### Integration Guides (Specific)
```
integrations/
├── shure-system-api.md              # Shure integration guide
└── [future-manufacturer].md         # Other manufacturers
```

## Files to Action

### Consolidate (Merge & Delete)
- [ ] `configuration.md` + `CONFIGURATION.md` → Keep newer `CONFIGURATION.md`, remove old
- [ ] `services.md` + `SERVICES_REFACTORING_SUMMARY.md` → Keep summary, archive old
- [ ] `shure-system-api-endpoints.md` → Merge into `api/endpoints.md`
- [ ] `VPN_DEVICE_POPULATION.md` → Archive (operation-specific)
- [ ] `services-quick-reference.md` → Keep as operations reference

### Archive (Move to historical)
- [ ] Development notes that are implementation-specific

### Keep & Enhance
- [ ] `architecture.md` - Core system design
- [ ] `plugin-development.md` - Developer guide
- [ ] `user-assignments.md` - Feature documentation
- [ ] `SHURE_NETWORK_GUID_TROUBLESHOOTING.md` - Critical troubleshooting

## Principles for Refactored Docs

1. **Clear Hierarchy**: From simple (quickstart) to complex (architecture)
2. **Task-Focused**: "How do I..." rather than "What is..."
3. **Concise**: Remove repetition, keep under 300 lines where possible
4. **Updated**: All examples current with working infrastructure
5. **Linked**: Cross-references between related docs
6. **Searchable**: Clear headings, consistent terminology

## Size Targets

- Quickstart: 50-100 lines
- Configuration: 100-150 lines
- Development guide: 100-150 lines
- Architecture: 200-300 lines
- API reference: 100-200 lines
- Advanced topics: 150-300 lines

## Timeline

1. **Phase 1**: Identify duplicates and outdated content (This list)
2. **Phase 2**: Consolidate files
3. **Phase 3**: Reorganize into clean structure
4. **Phase 4**: Update all examples to current infrastructure
5. **Phase 5**: Add missing troubleshooting guides
6. **Phase 6**: Create index/navigation

---

**Status**: Planning Phase
**Owner**: Refactoring Task
**Deadline**: Complete before moving to model testing
