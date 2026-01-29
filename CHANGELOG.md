# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Calendar Versioning](https://calver.org/).

## [Unreleased]

### Added

- **Configuration API** (`micboard.conf`): Centralized settings proxy for accessing Micboard configuration with consistent defaults
- **Architecture Documentation** (`micboard/ARCHITECTURE.md`): Comprehensive guide for developers on plugin architecture, multi-tenancy, and settings registry
- **Expanded Test Suite**: Tests for configuration module, plugin registry, and settings behavior
- **Comprehensive `.env.example`**: Template with all available Micboard configuration options and multi-tenancy settings
- **Enhanced README**: Detailed reusable app integration guide with plugin architecture examples
- **Comprehensive CONTRIBUTING.md**: Migration guidelines, code patterns, and development workflow documentation

### Changed

- **pyproject.toml**: Fixed package data inclusion for fixtures and migrations
- **MANIFEST.in**: Improved to include `.env.example` and exclude workspace-only files
- **.gitignore**: Enhanced to prevent tracking of development artifacts and egg-info directories
- **GitHub pre-commit hooks**: Added migration protection hook that prevents direct modification of migration files

### Fixed

- Configuration import consistency across app modules
- Whitespace issues in documentation and code examples

### Deprecated

- Direct use of `django.conf.settings.MICBOARD_*` – prefer `micboard.conf.config` for consistency

### Security

- Clarified that `.env` files should never be committed (already in `.gitignore`)
- Added reminder in CONTRIBUTING.md about AGPL licensing requirements for production use

### Documentation

- Reusable app integration guide in README.md
- Migration safety and lifecycle documentation
- Plugin architecture and settings registry patterns explained
- Development workflow and commit message guidelines

## [25.01.15] - 2026-01-15

### Added

- Initial beta release with multi-manufacturer support
- Device discovery and lifecycle management
- Alerting and performer assignment
- Real-time telemetry via WebSockets/SSE
- Multi-tenant support framework
- Settings registry with scope resolution
- Plugin architecture for manufacturer integration
