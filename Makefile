VERSION ?= $(shell tr -d '\r\n' < VERSION)
PYTHON ?= python3

.PHONY: test build-linux package-deb package-rpm packages-linux

test:
	$(PYTHON) -m unittest discover -s tests

build-linux:
	$(PYTHON) -m PyInstaller --noconfirm --clean TelegramAlertMonitor.spec

package-deb: build-linux
	tools/build-deb.sh "$(VERSION)" dist/TelegramAlertMonitor

package-rpm: build-linux
	tools/build-rpm.sh "$(VERSION)" dist/TelegramAlertMonitor

packages-linux: package-deb package-rpm
