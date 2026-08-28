#!/usr/bin/env bash
set -euo pipefail

version="${1:?Usage: build-rpm.sh VERSION EXECUTABLE_DIRECTORY}"
executable="${2:?Usage: build-rpm.sh VERSION EXECUTABLE_DIRECTORY}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
topdir="$root/build/rpm"

test -d "$executable"
command -v rpmbuild >/dev/null
rm -rf "$topdir"
install -d "$topdir/BUILD" "$topdir/BUILDROOT" "$topdir/RPMS" "$topdir/SOURCES" "$topdir/SPECS" "$topdir/SRPMS"
cp -a "$executable" "$topdir/SOURCES/TelegramAlertMonitor"
install -m 0644 "$root/config.example.toml" "$topdir/SOURCES/config.example.toml"
install -m 0644 "$root/deployment/telegram-alert-monitor.service" "$topdir/SOURCES/telegram-alert-monitor.service"
install -m 0644 "$root/packaging/telegram-alert-monitor.spec" "$topdir/SPECS/telegram-alert-monitor.spec"

rpmbuild -bb --define "_topdir $topdir" --define "app_version $version" "$topdir/SPECS/telegram-alert-monitor.spec"
cp "$topdir"/RPMS/*/telegram-alert-monitor-*.rpm "$root/dist/"
