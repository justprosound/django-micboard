# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
using Calendar Versioning (CalVer) in the format `YY.MM.DD`.

## [Unreleased]

### Added
- Services layer (DeviceService, SynchronizationService, LocationService, MonitoringService)
- Comprehensive test infrastructure with 95%+ coverage target
- Enhanced pytest configuration with coverage settings
- Pre-commit configuration for code quality automation
- GitHub Actions CI/CD workflows (tests, linting, security)
- GitHub Actions release workflow with CalVer versioning
- Development guide with testing and release procedures
- Architecture documentation with design recommendations
- Support for async services (future)
- Optional Django-Q background tasks support
- Optional Channels WebSocket support
- Optional GraphQL API support (planned)
- Optional Prometheus metrics support (planned)

### Changed
- Refactored business logic from signals to services layer
- Improved error handling and logging in services
- Enhanced test fixtures and factories
- Streamlined pytest configuration

### Fixed
- Battery level validation edge cases
- Device synchronization error handling
- Improved database transaction handling

### Deprecated
- Direct signal handlers (migrate to services layer)

### Removed
- None yet

### Security
- Added Bandit security scanning to CI/CD
- Added safety dependency checking
- Enhanced input validation in services

## [25.01.15] - 2025-01-15 (Example)

### Added
- Initial release preparation
- CalVer versioning scheme
- Release automation with PyPI publishing

### Changed
- Updated project structure for modular architecture

### Fixed
- Device state synchronization issues

## [25.01.01] - 2025-01-01 (Example)

### Added
- Initial Django Micboard release
- Multi-manufacturer support (Shure, Sennheiser)
- Real-time WebSocket updates
- Django REST Framework API
- Admin interface

---

## Version Format

This project uses Calendar Versioning (CalVer) with the format `YY.MM.DD`:

- `YY` = 2-digit year (25 = 2025)
- `MM` = 2-digit month (01 = January)
- `DD` = 2-digit day (15 = 15th)

Examples:
- `25.01.15` = Release on January 15, 2025
- `25.01.15.post1` = Post-release patch
- `25.01.15a1` = Alpha pre-release
- `25.01.15rc1` = Release candidate

## How to Update

1. Add changes to the `[Unreleased]` section
2. On release date, create new section with version and date
3. Update version in `pyproject.toml`
4. Tag release in git: `git tag v25.01.15`
5. Publish to PyPI

## Categories

- **Added**: New features
- **Changed**: Changes in existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security-related fixes and updates
