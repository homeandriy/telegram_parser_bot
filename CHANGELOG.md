# Changelog

## [Unreleased]

## v0.2.0 - 2026-08-28

### Added

- HTTP API for monitor health, pending event listing, and event acknowledgement.
- Stable event idempotency keys, persistent monitor status, and API configuration for the daemon.

### Changed

- Deployment configuration exposes the daemon HTTP API inside the Compose network.

### Fixed

- Release builds now include the PyInstaller specifications required by GitHub Actions.

## v0.1.0 - 2026-08-28

### Added

- Initial Telegram Alert Monitor release with desktop UI, configurable Telegram sources, alert scenarios, and deployment configuration.
