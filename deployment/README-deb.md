# Telegram Alert Monitor daemon package

This file applies to the DEB and RPM daemon packages used on Proxmox-hosted Linux guests.

## First configuration

```bash
sudo cp /etc/telegram-alert-monitor/config.example.toml /etc/telegram-alert-monitor/config.toml
sudo cp /etc/telegram-alert-monitor/environment.example /etc/telegram-alert-monitor/environment
sudoedit /etc/telegram-alert-monitor/config.toml
sudoedit /etc/telegram-alert-monitor/environment
```

Put `ALERTS_IN_UA_TOKEN` only in `environment`. The service reads it through systemd and does not store the token in TOML or Git.

Copy `resources.json` and `rules.json` from the desktop application to `/var/lib/telegram-alert-monitor/state/`, then set ownership:

```bash
sudo install -d -o telegram-monitor -g telegram-monitor /var/lib/telegram-alert-monitor/state
sudo install -o telegram-monitor -g telegram-monitor -m 0640 resources.json /var/lib/telegram-alert-monitor/state/resources.json
sudo install -o telegram-monitor -g telegram-monitor -m 0640 rules.json /var/lib/telegram-alert-monitor/state/rules.json
sudo systemctl enable --now telegram-alert-monitor
```

Each resource stores only `location_uid`: the alerts.in.ua UID of its rayon. The monitor resolves the oblast relation from its imported Location UID reference.

## Safe update

```bash
sudo systemctl stop telegram-alert-monitor
sudo cp /var/lib/telegram-alert-monitor/state/resources.json /var/lib/telegram-alert-monitor/resources.json.backup
sudo cp /var/lib/telegram-alert-monitor/state/rules.json /var/lib/telegram-alert-monitor/rules.json.backup
sudo dpkg -i telegram-alert-monitor_<version>_amd64.deb
sudo systemctl start telegram-alert-monitor
sudo systemctl status telegram-alert-monitor --no-pager
```

The package never overwrites `config.toml`, `environment`, the Telegram session, resources, rules, or the PostgreSQL data volume. For an RPM update, replace `dpkg -i …` with `sudo dnf install ./telegram-alert-monitor-<version>.rpm`.
