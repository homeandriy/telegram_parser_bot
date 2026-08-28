# Changelog

## [Unreleased]

## v0.3.3 - 2026-08-29

### Fixed

- RPM build now installs the systemd RPM macros required for the service-unit path.
- RHEL package builds include Qt plugin runtime libraries to avoid PyInstaller missing-library warnings.

## v0.3.2 - 2026-08-29

### Fixed

- Linux package build environments install Qt runtime libraries before PyInstaller analysis.

## v0.3.1 - 2026-08-29

### Fixed

- Linux Make targets now invoke package scripts through Bash on GitHub Actions.

## v0.3.0 - 2026-08-29

### Added

- Debian package for Debian, Ubuntu, and elementary OS installations.
- RHEL 9 compatible RPM package for Red Hat Enterprise Linux, Rocky Linux, AlmaLinux, and CentOS Stream.
- Make targets for Linux portable, DEB, and RPM builds.

### Changed

- Tagged GitHub releases now publish DEB and RPM assets alongside Windows and source archives.

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
