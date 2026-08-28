# Telegram Alert Monitor

Застосунок для персонального моніторингу заданих Telegram-каналів. Він має Qt UI для Windows та Ubuntu, а на Ubuntu також запускається без UI як daemon. PostgreSQL входить до Docker Compose стеку проєкту; окремо встановлювати або шукати сервер бази даних не потрібно.

> Це додатковий персональний сигнал, а не заміна офіційних систем сповіщення.

## Джерела

- `telethon` — основне джерело для публічних і доступних вашому акаунту приватних каналів.
- `t.me/s/` — резервне джерело без API-ключів тільки для публічних каналів.

## Перший запуск

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui,build]"
Copy-Item config.example.toml config.toml
.\.venv\Scripts\python.exe -m telegram_parser.app --config config.toml
```

Заповніть канали у `config.toml`. Для `telethon` також вкажіть `api_id`, `api_hash` та підготуйте session-файл окремо; не додавайте ці дані до Git.

## Ubuntu / Proxmox daemon з інтегрованим PostgreSQL

```bash
cd deployment
cp config.example.toml config.toml
# Скопіюйте сюди конфігурацію з UI Windows: resources.json і rules.json.
mkdir -p state
cp /path/to/resources.json /path/to/rules.json state/
# Відредагуйте config.toml: Telethon, PostgreSQL і webhook.
docker compose up -d --build
```

Compose піднімає два сервіси: `postgres` із постійним volume та `monitor` daemon. Їхня мережа внутрішня — PostgreSQL не публікує порт на хост.
Daemon раз на 30 секунд завантажує по 10 останніх повідомлень з кожного ресурсу, виконує сценарії з `state/rules.json` і записує попадання в `state/events.json`. Цей файл показує вкладка «Журнал» у UI на Ubuntu.

## Windows EXE

```powershell
.\.venv\Scripts\python.exe tools\create_icons.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name TelegramAlertMonitor --icon assets\telegram-alert.ico --add-data "assets;assets" --paths src src\launcher.py
```

## Windows installer

Після збірки EXE, якщо встановлено Inno Setup:

```powershell
.\tools\build-installer.ps1 -Version 0.1.0
```

## Release

Реліз запускається push-ем тега, який точно відповідає файлу `VERSION`:

```powershell
.\tools\build-release.ps1 -Version (Get-Content VERSION)
git add VERSION CHANGELOG.md .github\workflows\release.yml installer\telegram-alert-monitor.iss tools
git commit -m "chore(release): v0.1.0"
git tag v0.1.0
git push origin main v0.1.0
```

GitHub Actions виконує тести, створює portable Windows ZIP, Windows EXE-інсталятор та versioned source archive, а потім додає їх до GitHub Release.
