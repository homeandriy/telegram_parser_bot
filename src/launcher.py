"""PyInstaller-safe entry point for the packaged application."""

from telegram_parser.app import main


if __name__ == "__main__":
    raise SystemExit(main())
