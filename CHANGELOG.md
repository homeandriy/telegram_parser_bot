# Changelog

## [Unreleased]

## v0.6.1 - 2026-09-03

### Fixed

- Corrected setuptools package-data configuration so release builds can install the application.

## v0.6.0 - 2026-09-02

### Added

- Rule-level oblast and rayon selector backed by the bundled alerts.in.ua Location UID reference.
- `POST /api/rules/copy` and desktop flow to copy a rule to another channel with a different rayon or matching phrases.

### Changed

- Air-raid acceleration is determined by each rule location rather than by channel metadata.
- Empty incoming rule locations are normalized to Kyiv UID `31` before persistence.


## v0.5.0 - 2026-09-02

### Added

- Offline alerts.in.ua Location UID reference bundled into Windows EXE, Docker, DEB and RPM builds.
- Cascading desktop location selector: oblast, then rayon, with one stored rayon UID.
- Location API endpoints and channel metadata with automatically resolved parent oblast.
- DEB/RPM daemon environment template and safe Proxmox update guide.

### Changed

- Telegram polling uses alerts.in.ua only to accelerate resources whose configured rayon UID is under air raid.
- Application source is organized into application, alerts, api, core, desktop, domain, infrastructure and notifications packages.

## v0.4.0 - 2026-09-01

### Added

- Expo Push registration through `POST /api/mobile-devices` with per-rule sound preferences.
- Durable mobile-device subscriptions and idempotent Expo delivery records for alert events.

### Changed

- New rule matches dispatch mobile pushes only after the alert event is successfully stored.

### Fixed

- Alert-event retention is capped at 5,000 newest events.

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
