#!/usr/bin/env bash
set -euo pipefail

version="${1:?Usage: build-deb.sh VERSION EXECUTABLE_DIRECTORY}"
executable="${2:?Usage: build-deb.sh VERSION EXECUTABLE_DIRECTORY}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
package_root="$root/build/deb-root"

test -d "$executable"
rm -rf "$package_root"
install -d "$package_root/DEBIAN" "$package_root/opt/telegram-alert-monitor" "$package_root/usr/bin" "$package_root/etc/telegram-alert-monitor" "$package_root/lib/systemd/system"
cp -a "$executable/." "$package_root/opt/telegram-alert-monitor/"
ln -s /opt/telegram-alert-monitor/TelegramAlertMonitor "$package_root/usr/bin/telegram-alert-monitor"
install -m 0644 "$root/config.example.toml" "$package_root/etc/telegram-alert-monitor/config.example.toml"
install -m 0644 "$root/deployment/telegram-alert-monitor.service" "$package_root/lib/systemd/system/telegram-alert-monitor.service"

cat > "$package_root/DEBIAN/control" <<EOF
Package: telegram-alert-monitor
Version: $version
Section: utils
Priority: optional
Architecture: amd64
Maintainer: homeandriy
Description: Telegram Alert Monitor desktop and daemon application
EOF

cat > "$package_root/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -eu
getent group telegram-monitor >/dev/null 2>&1 || groupadd --system telegram-monitor
id -u telegram-monitor >/dev/null 2>&1 || useradd --system --gid telegram-monitor --home-dir /var/lib/telegram-alert-monitor --create-home --shell /usr/sbin/nologin telegram-monitor
install -d -o telegram-monitor -g telegram-monitor /var/lib/telegram-alert-monitor
systemctl daemon-reload >/dev/null 2>&1 || true
EOF
chmod 0755 "$package_root/DEBIAN/postinst"

dpkg-deb --build --root-owner-group "$package_root" "$root/dist/telegram-alert-monitor_${version}_amd64.deb"
