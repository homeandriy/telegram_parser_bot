"""Qt desktop interface for resources, rules, and settings."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import httpx
from telethon import TelegramClient
from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError

from PySide6.QtCore import QMimeData, QSize, QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QDrag, QIcon, QPixmap
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton,
    QPlainTextEdit, QScrollArea, QSpinBox, QSplitter, QStackedWidget, QStyle, QTabWidget, QTableWidget, QTableWidgetItem,
    QSystemTrayIcon, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .branding import asset_path
from .config import ChannelConfig
from .sources import PublicPreviewSource
from .state import Resource, StateRepository
from .ui_helpers import set_button_icon


def normalize_username(url: str) -> str:
    value = url.strip().rstrip("/")
    value = re.sub(r"^https?://t\.me/(s/)?", "", value, flags=re.IGNORECASE)
    return value.lstrip("@").split("?", 1)[0]


class ResourceTable(QTableWidget):
    rows_reordered = Signal(int, int)

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

    def startDrag(self, _supported_actions) -> None:  # type: ignore[override]
        row = self.currentRow()
        if row < 0:
            return
        mime = QMimeData()
        mime.setData("application/x-telegram-resource-row", str(row).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        if not event.mimeData().hasFormat("application/x-telegram-resource-row"):
            event.ignore()
            return
        source_row = int(bytes(event.mimeData().data("application/x-telegram-resource-row")).decode())
        target_row = self.indexAt(event.position().toPoint()).row()
        if target_row < 0:
            target_row = self.rowCount() - 1
        if source_row != target_row:
            self.rows_reordered.emit(source_row, target_row)
        event.acceptProposedAction()


class FetchWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, resource: Resource, limit: int) -> None:
        super().__init__()
        self.resource = resource
        self.limit = limit

    def run(self) -> None:
        try:
            if self.resource.sync_type != "public":
                raise ValueError("Telethon API ресурс тестується та синхронізується на серверному daemon після налаштування сесії.")
            channel = ChannelConfig(self.resource.name, self.resource.username, "public")
            messages = asyncio.run(PublicPreviewSource(self.limit).fetch(channel))
            self.completed.emit(messages)
        except Exception as error:
            self.failed.emit(str(error))


class TelethonAuthWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, api_id: int, api_hash: str, phone: str, code: str, session_path: str) -> None:
        super().__init__()
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.code = code
        self.session_path = session_path

    def run(self) -> None:
        asyncio.run(self.authenticate())

    async def authenticate(self) -> None:
        client = TelegramClient(self.session_path, self.api_id, self.api_hash)
        try:
            await client.connect()
            if await client.is_user_authorized():
                account = await client.get_me()
                self.completed.emit(f"Авторизацію перевірено: {account.first_name or account.username or account.id}")
                return
            if not self.code:
                await client.send_code_request(self.phone)
                self.completed.emit("Код входу надіслано в Telegram. Введіть його нижче та ще раз натисніть «Тест / увійти».")
                return
            await client.sign_in(phone=self.phone, code=self.code)
            account = await client.get_me()
            self.completed.emit(f"Вхід виконано: {account.first_name or account.username or account.id}")
        except SessionPasswordNeededError:
            self.failed.emit("Для цього акаунта увімкнено двоетапну перевірку. Підтримку пароля 2FA потрібно додати окремо.")
        except PhoneCodeInvalidError:
            self.failed.emit("Невірний або застарілий код. Запросіть новий код кнопкою «Тест / увійти».")
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            await client.disconnect()


class OpenMediaWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def run(self) -> None:
        try:
            response = httpx.get(self.url, timeout=30, follow_redirects=True, headers={"User-Agent": "TelegramAlertMonitor/0.1"})
            response.raise_for_status()
            suffix = Path(urlparse(str(response.url)).path).suffix
            if not suffix:
                suffix = mimetypes.guess_extension(response.headers.get("content-type", "").split(";", 1)[0]) or ".bin"
            media_dir = Path(tempfile.gettempdir()) / "TelegramAlertMonitor"
            media_dir.mkdir(parents=True, exist_ok=True)
            target = media_dir / f"telegram-media-{abs(hash(self.url))}{suffix}"
            target.write_bytes(response.content)
            self.completed.emit(str(target))
        except httpx.HTTPError as error:
            self.failed.emit(str(error))


class ImagePreviewWorker(QThread):
    completed = Signal(str, bytes)
    failed = Signal(str, str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def run(self) -> None:
        try:
            timeout = httpx.Timeout(8.0, connect=5.0)
            with httpx.stream("GET", self.url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "TelegramAlertMonitor/0.1"}) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 12 * 1024 * 1024:
                        raise ValueError("файл більший за 12 МБ; відкрийте його кнопкою «Переглянути»")
                    chunks.append(chunk)
            self.completed.emit(self.url, b"".join(chunks))
        except (httpx.HTTPError, ValueError) as error:
            self.failed.emit(self.url, str(error))


class AddResourceDialog(QDialog):
    def __init__(self, fetch: Callable[[Resource, int, Callable], None], resource: Resource | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.fetch = fetch
        self.editing_resource = resource
        self.tested_resource: Resource | None = resource
        self.setWindowTitle("Редагувати ресурс" if resource else "Додати ресурс")
        self.setMinimumWidth(500)
        self.url = QLineEdit(placeholderText="https://t.me/channel або @channel")
        self.sync_type = QComboBox()
        self.sync_type.addItem("Публічний t.me/s/", "public")
        self.sync_type.addItem("Telegram API / Telethon", "telethon")
        self.name = QLineEdit(placeholderText="За замовчуванням — назва каналу")
        self.description = QPlainTextEdit()
        self.description.setPlaceholderText("Необов’язковий особистий опис")
        if resource:
            self.url.setText(resource.url)
            self.sync_type.setCurrentIndex(max(0, self.sync_type.findData(resource.sync_type)))
            self.name.setText(resource.name)
            self.description.setPlainText(resource.description)
        self.test_button = QPushButton("Тест: завантажити 10 останніх")
        set_button_icon(self.test_button, QStyle.StandardPixmap.SP_BrowserReload, "Перевірити ресурс та отримати 10 останніх повідомлень")
        self.test_button.clicked.connect(self.test_resource)
        self.result = QLabel("Спочатку протестуйте ресурс.")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        self.add_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.add_button.setText("Зберегти зміни" if resource else "Додати ресурс")
        set_button_icon(self.add_button, QStyle.StandardPixmap.SP_DialogSaveButton if resource else QStyle.StandardPixmap.SP_FileDialogNewFolder, "Зберегти зміни ресурсу" if resource else "Додати перевірений ресурс")
        set_button_icon(buttons.button(QDialogButtonBox.StandardButton.Cancel), QStyle.StandardPixmap.SP_DialogCancelButton, "Скасувати додавання ресурсу")
        self.add_button.setEnabled(resource is not None)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout()
        form.addRow("URL", self.url)
        form.addRow("Тип синхронізації", self.sync_type)
        form.addRow("Назва", self.name)
        form.addRow("Опис", self.description)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.test_button)
        layout.addWidget(self.result)
        layout.addWidget(buttons)

    def resource(self) -> Resource:
        username = normalize_username(self.url.text())
        return Resource(
            id=self.tested_resource.id if self.tested_resource else (self.editing_resource.id if self.editing_resource else ""),
            url=self.url.text().strip(),
            username=username,
            sync_type=str(self.sync_type.currentData()),
            name=self.name.text().strip() or username,
            description=self.description.toPlainText().strip(),
        )

    def test_resource(self) -> None:
        resource = self.resource()
        if not resource.username:
            self.result.setText("Вкажіть коректний URL або username.")
            return
        self.test_button.setEnabled(False)
        self.result.setText("Тестування…")
        self.fetch(resource, 10, self.test_finished)

    def test_finished(self, messages: object, error: str | None) -> None:
        self.test_button.setEnabled(True)
        if error:
            self.result.setText(f"Помилка: {error}")
            return
        if not messages:
            self.result.setText("Ресурс доступний, але повідомлень не знайдено.")
            return
        resource = self.resource()
        resource.id = self.tested_resource.id if self.tested_resource else __import__("uuid").uuid4().hex
        self.tested_resource = resource
        self.add_button.setEnabled(True)
        self.result.setText(f"Успішно: отримано {len(messages)} повідомлень. Зміни можна зберегти.")


class MainWindow(QMainWindow):
    def __init__(self, repository: StateRepository) -> None:
        super().__init__()
        self.repository = repository
        self.resources = repository.load_resources()
        self.rules = repository.load_rules()
        self.messages: dict[str, dict[str, object]] = {}
        self.workers: list[FetchWorker] = []
        self.telethon_auth_workers: list[TelethonAuthWorker] = []
        self.media_workers: list[OpenMediaWorker] = []
        self.preview_workers: list[ImagePreviewWorker] = []
        self.setWindowTitle("Telegram Alert Monitor")
        self.brand_icon = QIcon(str(asset_path("telegram-alert.ico")))
        self.setWindowIcon(self.brand_icon)
        self.tray = QSystemTrayIcon(self.brand_icon, self)
        self.tray.setToolTip("Telegram Alert Monitor")
        self.tray.show()
        self.resize(1280, 760)
        self.tabs = QTabWidget()
        self.tabs.setIconSize(QSize(28, 28))
        self.tabs.setStyleSheet("QTabBar::tab { min-height: 40px; padding: 8px 20px; font-size: 15px; }")
        style = self.style()
        self.tabs.addTab(self.channels_tab(), style.standardIcon(QStyle.StandardPixmap.SP_DirIcon), "Канали")
        self.tabs.addTab(self.rules_tab(), style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "Правила")
        self.tabs.addTab(self.settings_tab(), style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView), "Налаштування")
        self.tabs.addTab(self.logs_tab(), style.standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView), "Журнал")
        self.setCentralWidget(self.tabs)
        self.refresh_resources()

    def channels_tab(self) -> QWidget:
        tab = QWidget()
        self.resource_table = ResourceTable(0, 3)
        self.resource_table.setHorizontalHeaderLabels(["Назва", "Канал", "Опис"])
        self.resource_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.resource_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.resource_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.resource_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.resource_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.resource_table.itemSelectionChanged.connect(self.resource_selected)
        self.resource_table.itemDoubleClicked.connect(lambda _item: self.edit_resource())
        self.resource_table.rows_reordered.connect(self.reorder_resources)
        add_button = QPushButton("Додати ресурс")
        set_button_icon(add_button, QStyle.StandardPixmap.SP_FileDialogNewFolder, "Додати новий Telegram-ресурс")
        add_button.clicked.connect(self.add_resource)
        edit_button = QPushButton("Редагувати ресурс")
        set_button_icon(edit_button, QStyle.StandardPixmap.SP_FileDialogDetailedView, "Відкрити вибраний ресурс у вікні редагування")
        edit_button.clicked.connect(self.edit_resource)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        brand = QLabel()
        brand.setPixmap(QPixmap(str(asset_path("telegram-alert.png"))).scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        brand.setToolTip("Telegram Alert Monitor")
        left_layout.addWidget(brand)
        left_layout.addWidget(QLabel("Ресурси (перетягуйте для сортування)"))
        left_layout.addWidget(self.resource_table)
        left_layout.addWidget(edit_button)
        left_layout.addWidget(add_button)
        self.message_table = QTableWidget(0, 4)
        self.message_table.setHorizontalHeaderLabels(["Дата", "ID", "Повідомлення", "Медіа"])
        self.message_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.message_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.message_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.message_table.setWordWrap(True)
        self.message_table.itemSelectionChanged.connect(self.message_selected)
        self.message_preview = QPlainTextEdit(readOnly=True)
        self.message_preview.setPlaceholderText("Виберіть повідомлення, щоб переглянути його повністю.")
        self.media_label = QLabel("Для вибраного повідомлення немає фото чи відео.")
        self.media_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.media_label.setMinimumHeight(160)
        self.media_scroll = QScrollArea()
        self.media_scroll.setWidgetResizable(True)
        self.media_scroll.setWidget(self.media_label)
        self.video_widget = QVideoWidget()
        self.video_player = QMediaPlayer(self)
        self.video_player.setVideoOutput(self.video_widget)
        self.media_stack = QStackedWidget()
        self.media_stack.addWidget(self.media_scroll)
        self.media_stack.addWidget(self.video_widget)
        self.media_picker = QComboBox()
        self.media_picker.setEnabled(False)
        self.media_picker.currentIndexChanged.connect(self.media_changed)
        self.open_media_button = QPushButton("Переглянути")
        set_button_icon(self.open_media_button, QStyle.StandardPixmap.SP_DialogOpenButton, "Відкрити вибраний файл стандартною програмою Windows")
        self.open_media_button.setEnabled(False)
        self.open_media_button.clicked.connect(self.open_selected_media)
        preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        preview_splitter.addWidget(self.message_preview)
        media_panel = QWidget()
        media_layout = QVBoxLayout(media_panel)
        media_layout.addWidget(self.media_picker)
        media_layout.addWidget(self.open_media_button)
        media_layout.addWidget(self.media_stack)
        preview_splitter.addWidget(media_panel)
        preview_splitter.setSizes([600, 300])
        self.count_input = QSpinBox()
        self.count_input.setRange(1, 1000)
        self.count_input.setValue(20)
        self.download_button = QPushButton("Завантажити повідомлення")
        set_button_icon(self.download_button, QStyle.StandardPixmap.SP_BrowserReload, "Завантажити останні повідомлення вибраного ресурсу")
        self.download_button.clicked.connect(self.download_messages)
        bottom = QHBoxLayout()
        bottom.addWidget(self.download_button)
        bottom.addStretch(1)
        bottom.addWidget(QLabel("Кількість останніх:"))
        bottom.addWidget(self.count_input)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Повідомлення вибраного ресурсу"))
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(self.message_table)
        right_splitter.addWidget(preview_splitter)
        right_splitter.setSizes([410, 230])
        right_layout.addWidget(right_splitter)
        right_layout.addLayout(bottom)
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([430, 850])
        layout = QVBoxLayout(tab)
        layout.addWidget(splitter)
        return tab

    def rules_tab(self) -> QWidget:
        tab = QWidget()
        self.rule_resources = QListWidget()
        self.rule_resources.currentRowChanged.connect(self.rule_resource_selected)
        self.rule_tree = QTreeWidget()
        self.rule_tree.setHeaderLabels(["Умова / група", "Логіка"])
        rule_header = self.rule_tree.header()
        rule_header.setStretchLastSection(False)
        rule_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        rule_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.rule_tree.itemSelectionChanged.connect(self.rule_tree_selection_changed)
        add_contains = QPushButton("Додати «містить»")
        set_button_icon(add_contains, QStyle.StandardPixmap.SP_FileDialogNewFolder, "Додати умову «повідомлення містить»")
        add_contains.clicked.connect(lambda: self.add_condition("contains"))
        add_not = QPushButton("Додати «не містить»")
        set_button_icon(add_not, QStyle.StandardPixmap.SP_FileDialogNewFolder, "Додати умову «повідомлення не містить»")
        add_not.clicked.connect(lambda: self.add_condition("not_contains"))
        add_group = QPushButton("Відкрити вкладену групу ( )")
        set_button_icon(add_group, QStyle.StandardPixmap.SP_DirOpenIcon, "Додати вкладену групу умов")
        add_group.clicked.connect(self.add_group)
        add_scenario = QPushButton("Додати сценарій (АБО)")
        set_button_icon(add_scenario, QStyle.StandardPixmap.SP_FileDialogNewFolder, "Додати незалежний сценарій для вибраного каналу")
        add_scenario.clicked.connect(self.add_scenario)
        edit_condition = QPushButton("Редагувати умову")
        set_button_icon(edit_condition, QStyle.StandardPixmap.SP_FileDialogDetailedView, "Змінити текст вибраної умови")
        edit_condition.clicked.connect(self.edit_condition)
        remove = QPushButton("Видалити")
        set_button_icon(remove, QStyle.StandardPixmap.SP_TrashIcon, "Видалити вибрану умову або групу")
        remove.clicked.connect(self.remove_rule_item)
        validate = QPushButton("Валідувати")
        set_button_icon(validate, QStyle.StandardPixmap.SP_DialogApplyButton, "Перевірити правило")
        validate.clicked.connect(self.validate_rule)
        technical = QPushButton("Показати технічно")
        set_button_icon(technical, QStyle.StandardPixmap.SP_MessageBoxInformation, "Показати JSON правила")
        technical.clicked.connect(self.show_technical_rule)
        self.group_operator = QComboBox()
        self.group_operator.addItem("І", "and")
        self.group_operator.addItem("АБО", "or")
        self.group_operator.currentIndexChanged.connect(self.update_group_operator)
        actions = QGroupBox("Дія після збігу групи")
        form = QFormLayout(actions)
        self.action_type = QComboBox()
        self.action_type.addItems(["POST", "GET"])
        self.action_url = QLineEdit(placeholderText="https://… (необов’язково)")
        self.action_headers = QPlainTextEdit(placeholderText='{"Authorization": "Bearer …"}')
        self.action_headers.setMaximumHeight(60)
        self.action_body = QPlainTextEdit(placeholderText='{"event": "critical"}')
        self.action_body.setMaximumHeight(60)
        self.tray_action = QCheckBox("Показати повідомлення в треї")
        self.sound_action = QCheckBox("Відтворити звук")
        save_action = QPushButton("Зберегти дію")
        set_button_icon(save_action, QStyle.StandardPixmap.SP_DialogSaveButton, "Зберегти дію для вибраної групи")
        save_action.clicked.connect(self.save_action)
        form.addRow("Метод", self.action_type)
        form.addRow("URL", self.action_url)
        form.addRow("Headers (JSON)", self.action_headers)
        form.addRow("Body (JSON)", self.action_body)
        form.addRow(self.tray_action)
        form.addRow(self.sound_action)
        form.addRow(save_action)
        controls = QGridLayout()
        controls.addWidget(QLabel("Оператор поточної групи:"), 0, 0)
        controls.addWidget(self.group_operator, 0, 1)
        controls.addWidget(add_contains, 1, 0)
        controls.addWidget(add_not, 1, 1)
        controls.addWidget(add_group, 2, 0, 1, 2)
        controls.addWidget(add_scenario, 3, 0, 1, 2)
        controls.addWidget(edit_condition, 4, 0)
        controls.addWidget(remove, 4, 1)
        controls.addWidget(validate, 5, 0)
        controls.addWidget(technical, 5, 1)
        left = QWidget(); left_layout = QVBoxLayout(left); left_layout.addWidget(QLabel("Ресурси")); left_layout.addWidget(self.rule_resources)
        right = QWidget(); right_layout = QVBoxLayout(right); right_layout.addWidget(QLabel("Конструктор правил")); right_layout.addWidget(self.rule_tree, 1); right_layout.addLayout(controls); right_layout.addWidget(actions)
        splitter = QSplitter(); splitter.addWidget(left); splitter.addWidget(right); splitter.setSizes([300, 900])
        layout = QVBoxLayout(tab); layout.addWidget(splitter)
        return tab

    def settings_tab(self) -> QWidget:
        tab = QWidget(); settings = self.repository.load_settings()
        self.api_port = QSpinBox(); self.api_port.setRange(1024, 65535); self.api_port.setValue(int(settings["api_port"]))
        self.language = QComboBox(); self.language.addItem("Українська", "uk"); self.language.addItem("English", "en"); self.language.addItem("Polski", "pl")
        self.language.setCurrentIndex(max(0, self.language.findData(settings["language"])))
        save = QPushButton("Зберегти налаштування"); set_button_icon(save, QStyle.StandardPixmap.SP_DialogSaveButton, "Зберегти API-порт, мову та параметри Telethon"); save.clicked.connect(self.save_settings)
        app_form = QFormLayout(); app_form.addRow("API порт", self.api_port); app_form.addRow("Мова", self.language); app_form.addRow(save)

        telethon_group = QGroupBox("Telegram API / Telethon")
        telethon_form = QFormLayout(telethon_group)
        self.telethon_api_id = QLineEdit(str(settings["telethon_api_id"]), placeholderText="Наприклад: 12345678")
        self.telethon_api_id.setInputMask("99999999999;_")
        self.telethon_api_hash = QLineEdit(str(settings["telethon_api_hash"]), placeholderText="32 символи")
        self.telethon_api_hash.setEchoMode(QLineEdit.EchoMode.Password)
        self.telethon_phone = QLineEdit(str(settings["telethon_phone"]), placeholderText="+380…")
        self.telethon_code = QLineEdit(placeholderText="Одноразовий код із Telegram")
        self.telethon_code.setEchoMode(QLineEdit.EchoMode.Password)
        self.telethon_session_path = QLineEdit(str(settings["telethon_session_path"]))
        self.telethon_status = QLabel("Вкажіть ключі та номер, потім натисніть «Тест / увійти».")
        self.telethon_status.setWordWrap(True)
        self.telethon_test = QPushButton("Тест / увійти")
        set_button_icon(self.telethon_test, QStyle.StandardPixmap.SP_DialogApplyButton, "Перевірити ключі Telegram API та авторизувати локальну сесію")
        self.telethon_test.clicked.connect(self.test_telethon)
        guide = QLabel(
            '<ol>'
            '<li>Відкрийте <a href="https://my.telegram.org/apps">my.telegram.org/apps</a> і увійдіть у Telegram.</li>'
            '<li>Створіть <i>Application</i> та скопіюйте <b>API ID</b> і <b>API Hash</b>.</li>'
            '<li>Вкажіть номер телефону в міжнародному форматі, наприклад <code>+380…</code>.</li>'
            '<li>Натисніть «Тест / увійти». Код надійде в Telegram.</li>'
            '<li>Введіть код і повторно натисніть «Тест / увійти».</li>'
            '</ol>'
            '<p><b>Локально:</b> API Hash і номер зберігаються у <code>config/settings.toml</code>. Код входу не зберігається.</p>'
        )
        guide.setOpenExternalLinks(True)
        guide.setWordWrap(True)
        telethon_form.addRow("API ID", self.telethon_api_id)
        telethon_form.addRow("API Hash", self.telethon_api_hash)
        telethon_form.addRow("Номер телефону", self.telethon_phone)
        telethon_form.addRow("Код Telegram", self.telethon_code)
        telethon_form.addRow("Файл сесії", self.telethon_session_path)
        telethon_form.addRow(self.telethon_test)
        telethon_form.addRow("Статус", self.telethon_status)
        telethon_form.addRow("Інструкція", guide)
        layout = QVBoxLayout(tab); layout.addWidget(QLabel("Налаштування застосунку")); layout.addLayout(app_form); layout.addWidget(telethon_group); layout.addStretch(1)
        return tab

    def logs_tab(self) -> QWidget:
        tab = QWidget()
        self.events_table = QTableWidget(0, 5)
        self.events_table.setHorizontalHeaderLabels(["Час", "Ресурс", "Сценарій", "Збіг", "Результат дії"])
        self.events_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.events_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        refresh = QPushButton("Оновити журнал")
        set_button_icon(refresh, QStyle.StandardPixmap.SP_BrowserReload, "Оновити записи про попадання в правила")
        refresh.clicked.connect(self.refresh_event_log)
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Журнал попадань у правила"))
        layout.addWidget(self.events_table)
        layout.addWidget(refresh)
        self.refresh_event_log()
        return tab

    def refresh_event_log(self) -> None:
        if not hasattr(self, "events_table"):
            return
        events = self.repository.load_events()
        self.events_table.setRowCount(0)
        for row, event in enumerate(events):
            self.events_table.insertRow(row)
            values = (
                str(event.get("created_at", "")),
                str(event.get("resource", "")),
                f"Сценарій {event.get('scenario', '')}",
                ", ".join(event.get("matched", [])),
                str(event.get("action", "")),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 3:
                    item.setToolTip(str(event.get("message", "")))
                self.events_table.setItem(row, column, item)

    def refresh_resources(self) -> None:
        current_id = self.selected_resource_id()
        self.resource_table.setRowCount(0); self.rule_resources.clear()
        for row, resource in enumerate(self.resources):
            self.resource_table.insertRow(row)
            for column, value in enumerate((resource.name, f"@{resource.username}", resource.description)):
                item = QTableWidgetItem(value)
                if column == 0: item.setData(Qt.ItemDataRole.UserRole, resource.id)
                self.resource_table.setItem(row, column, item)
            self.rule_resources.addItem(resource.name)
            self.rule_resources.item(row).setData(Qt.ItemDataRole.UserRole, resource.id)
            if resource.id == current_id:
                self.resource_table.selectRow(row); self.rule_resources.setCurrentRow(row)
        if self.resources and self.resource_table.currentRow() < 0:
            self.resource_table.selectRow(0); self.rule_resources.setCurrentRow(0)

    def selected_resource_id(self) -> str | None:
        row = self.resource_table.currentRow() if hasattr(self, "resource_table") else -1
        return self.resource_table.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 and self.resource_table.item(row, 0) else None

    def selected_resource(self) -> Resource | None:
        selected_id = self.selected_resource_id()
        return next((resource for resource in self.resources if resource.id == selected_id), None)

    def resource_selected(self) -> None:
        resource = self.selected_resource()
        if resource is None: return
        self.rule_resources.setCurrentRow(self.resource_table.currentRow())
        self.show_messages(resource)

    def reorder_resources(self, source_row: int, target_row: int) -> None:
        if not (0 <= source_row < len(self.resources) and 0 <= target_row < len(self.resources)):
            return
        resource = self.resources.pop(source_row)
        self.resources.insert(target_row, resource)
        self.repository.save_resources(self.resources)
        self.refresh_resources()
        self.resource_table.selectRow(target_row)

    def start_fetch(self, resource: Resource, limit: int, callback: Callable[[object, str | None], None]) -> None:
        worker = FetchWorker(resource, limit)
        self.workers.append(worker)
        worker.completed.connect(lambda messages: callback(messages, None))
        worker.failed.connect(lambda error: callback([], error))
        worker.finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()

    def add_resource(self) -> None:
        dialog = AddResourceDialog(self.start_fetch, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.tested_resource is not None:
            self.resources.append(dialog.tested_resource)
            self.repository.save_resources(self.resources)
            self.refresh_resources()
            self.resource_table.selectRow(len(self.resources) - 1)

    def edit_resource(self) -> None:
        resource = self.selected_resource()
        if resource is None:
            QMessageBox.information(self, "Редагування ресурсу", "Спочатку виберіть ресурс у списку.")
            return
        dialog = AddResourceDialog(self.start_fetch, resource, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.resource()
        for index, item in enumerate(self.resources):
            if item.id == resource.id:
                self.resources[index] = updated
                break
        self.repository.save_resources(self.resources)
        self.refresh_resources()
        row = next((index for index, item in enumerate(self.resources) if item.id == updated.id), 0)
        self.resource_table.selectRow(row)

    def download_messages(self) -> None:
        resource = self.selected_resource()
        if resource is None: return
        self.download_button.setEnabled(False)
        self.download_button.setText("Завантаження…")
        self.start_fetch(resource, self.count_input.value(), self.messages_downloaded)

    def messages_downloaded(self, messages: object, error: str | None) -> None:
        self.download_button.setEnabled(True); self.download_button.setText("Завантажити повідомлення")
        if error:
            QMessageBox.critical(self, "Помилка синхронізації", error); return
        resource = self.selected_resource()
        if resource is None: return
        cache = self.messages.setdefault(resource.id, {})
        for message in messages: cache[message.external_id] = message
        self.show_messages(resource)

    def show_messages(self, resource: Resource) -> None:
        records = sorted(self.messages.get(resource.id, {}).values(), key=lambda message: int(message.external_id), reverse=True)
        self.message_table.setRowCount(0)
        for row, message in enumerate(records):
            self.message_table.insertRow(row)
            self.message_table.setItem(row, 0, QTableWidgetItem(message.published_at.isoformat() if message.published_at else ""))
            self.message_table.setItem(row, 1, QTableWidgetItem(message.external_id))
            self.message_table.setItem(row, 2, QTableWidgetItem(message.text))
            self.message_table.setItem(row, 3, QTableWidgetItem(f"{len(message.media_urls)} фото, {len(message.video_urls)} відео"))
            self.message_table.setRowHeight(row, 34)

    def message_selected(self) -> None:
        resource = self.selected_resource()
        row = self.message_table.currentRow()
        if resource is None or row < 0:
            return
        message_id_item = self.message_table.item(row, 1)
        if message_id_item is None:
            return
        message = self.messages.get(resource.id, {}).get(message_id_item.text())
        if message is None:
            return
        self.message_preview.setPlainText(message.text)
        self.video_player.stop()
        self.media_picker.blockSignals(True)
        self.media_picker.clear()
        # A video is the most urgent/expressive attachment, so select it first.
        # Nothing is fetched until the user explicitly asks to open the file.
        for index, url in enumerate(message.video_urls, start=1):
            self.media_picker.addItem(f"Відео {index}", ("video", url))
        for index, url in enumerate(message.media_urls, start=1):
            self.media_picker.addItem(f"Фото {index}", ("image", url))
        self.media_picker.blockSignals(False)
        self.media_picker.setEnabled(self.media_picker.count() > 0)
        self.open_media_button.setEnabled(self.media_picker.count() > 0)
        if self.media_picker.count() == 0:
            self.media_label.setText("Для вибраного повідомлення немає фото чи відео.")
            self.media_stack.setCurrentWidget(self.media_scroll)
            return
        self.media_picker.setCurrentIndex(0)
        self.load_selected_media()

    def media_changed(self) -> None:
        self.load_selected_media()

    def load_selected_media(self) -> None:
        data = self.media_picker.currentData()
        if not data:
            return
        kind, url = data
        if kind == "video":
            self.media_stack.setCurrentWidget(self.video_widget)
            self.video_player.setSource(QUrl(url))
            self.video_player.play()
            return
        self.media_stack.setCurrentWidget(self.media_scroll)
        self.media_label.setPixmap(QPixmap())
        self.media_label.setText("Завантаження зображення…")
        worker = ImagePreviewWorker(url)
        self.preview_workers.append(worker)
        worker.completed.connect(self.show_image_preview)
        worker.failed.connect(self.image_preview_failed)
        worker.finished.connect(lambda: self.preview_workers.remove(worker) if worker in self.preview_workers else None)
        worker.start()

    def show_image_preview(self, url: str, payload: bytes) -> None:
        current = self.media_picker.currentData()
        if not current or current[0] != "image" or current[1] != url:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(payload):
            self.media_label.setText("Отриманий файл не є зображенням. Відкрийте його кнопкою «Переглянути».")
            return
        self.media_label.setPixmap(pixmap.scaled(540, 420, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def image_preview_failed(self, url: str, error: str) -> None:
        current = self.media_picker.currentData()
        if current and current[0] == "image" and current[1] == url:
            self.media_label.setText(f"Прев’ю не завантажилося за 8 секунд. Відкрийте файл кнопкою «Переглянути».\n{error}")

    def open_selected_media(self) -> None:
        data = self.media_picker.currentData()
        if not data:
            return
        kind, url = data
        label = "відео" if kind == "video" else "зображення"
        self.open_media_button.setEnabled(False)
        self.media_label.setText(f"Підготовка {label} для перегляду…")
        worker = OpenMediaWorker(url)
        self.media_workers.append(worker)
        worker.completed.connect(self.open_local_media)
        worker.failed.connect(self.media_open_failed)
        worker.finished.connect(lambda: self.media_workers.remove(worker) if worker in self.media_workers else None)
        worker.start()

    def open_local_media(self, path: str) -> None:
        self.open_media_button.setEnabled(True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self.media_label.setText("Windows не зміг відкрити файл стандартною програмою.")
            return
        self.media_label.setText("Файл відкрито стандартною програмою Windows.")

    def media_open_failed(self, error: str) -> None:
        self.open_media_button.setEnabled(True)
        self.media_label.setText(f"Не вдалося підготувати медіафайл: {error}")

    def rule_resource_selected(self, row: int) -> None:
        if row < 0: return
        self.load_rule_tree(self.rule_resource_id())

    def rule_resource_id(self) -> str | None:
        item = self.rule_resources.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def current_rule(self) -> dict:
        resource_id = self.rule_resource_id()
        if resource_id is None: return {"operator": "and", "items": [], "action": {}}
        return self.rules.setdefault(resource_id, {"operator": "and", "items": [], "action": {"method": "POST", "url": "", "headers": "{}", "body": "{}", "tray": True, "sound": True}})

    def load_rule_tree(self, _resource_id: str | None) -> None:
        self.rule_tree.clear(); rule = self.current_rule(); root = self.tree_item(rule, is_root=True); self.rule_tree.addTopLevelItem(root); root.setExpanded(True)
        self.group_operator.setCurrentIndex(max(0, self.group_operator.findData(rule.get("operator", "and"))))
        self.load_action(rule)

    def tree_item(self, node: dict, is_root: bool = False) -> QTreeWidgetItem:
        if node.get("type") == "condition":
            item = QTreeWidgetItem([f"Повідомлення {'містить' if node['mode'] == 'contains' else 'не містить'}: {node['value']}", ""])
            item.setData(0, Qt.ItemDataRole.UserRole, node)
            return item
        title = "Сценарії каналу" if is_root else ("Окремий сценарій" if node.get("scenario") else "( вкладена група )")
        item = QTreeWidgetItem([title, "І" if node.get("operator") == "and" else "АБО"])
        item.setData(0, Qt.ItemDataRole.UserRole, node)
        for child in node.get("items", []): item.addChild(self.tree_item(child))
        return item

    def add_condition(self, mode: str) -> None:
        value, ok = QInputDialog.getText(self, "Нова умова", "Текст для порівняння:")
        if ok and value.strip():
            self.target_group()["items"].append({"type": "condition", "mode": mode, "value": value.strip()})
            self.save_rules(); self.load_rule_tree(self.rule_resource_id())

    def add_group(self) -> None:
        self.target_group()["items"].append({"type": "group", "operator": "and", "items": [], "action": self.default_action()})
        self.save_rules(); self.load_rule_tree(self.rule_resource_id())

    def add_scenario(self) -> None:
        """Append an independent OR branch with its first condition."""
        value, ok = QInputDialog.getText(self, "Новий сценарій", "Перша умова «повідомлення містить»:")
        if not ok or not value.strip():
            return
        rule = self.current_rule()
        scenario = {
            "type": "group",
            "scenario": True,
            "operator": "and",
            "items": [{"type": "condition", "mode": "contains", "value": value.strip()}],
            "action": self.default_action(),
        }
        rule["items"].append(scenario)
        self.save_rules()
        self.load_rule_tree(self.rule_resource_id())
        root = self.rule_tree.topLevelItem(0)
        if root is not None:
            self.rule_tree.setCurrentItem(root.child(root.childCount() - 1))

    def edit_condition(self) -> None:
        item = self.rule_tree.currentItem()
        if item is None:
            QMessageBox.information(self, "Редагування", "Виберіть умову в дереві правил.")
            return
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node.get("type") != "condition":
            QMessageBox.information(self, "Редагування", "Для сценарію або групи редагуйте умови та дію нижче.")
            return
        value, ok = QInputDialog.getText(self, "Редагувати умову", "Текст для порівняння:", text=node.get("value", ""))
        if ok and value.strip():
            node["value"] = value.strip()
            self.save_rules()
            self.load_rule_tree(self.rule_resource_id())

    def remove_rule_item(self) -> None:
        item = self.rule_tree.currentItem()
        if item is None: return
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node is self.current_rule():
            QMessageBox.information(self, "Правила", "Кореневу групу видалити не можна."); return
        if self.remove_node(self.current_rule(), node):
            self.save_rules(); self.load_rule_tree(self.rule_resource_id())

    def update_group_operator(self) -> None:
        if self.rule_resources.currentRow() < 0: return
        self.target_group()["operator"] = self.group_operator.currentData(); self.save_rules(); self.load_rule_tree(self.rule_resource_id())

    def save_action(self) -> None:
        self.target_group()["action"] = {"method": self.action_type.currentText(), "url": self.action_url.text().strip(), "headers": self.action_headers.toPlainText().strip() or "{}", "body": self.action_body.toPlainText().strip() or "{}", "tray": self.tray_action.isChecked(), "sound": self.sound_action.isChecked()}
        self.save_rules(); QMessageBox.information(self, "Збережено", "Дію правила збережено.")

    def save_rules(self) -> None:
        self.repository.save_rules(self.rules)

    @staticmethod
    def default_action() -> dict:
        return {"method": "POST", "url": "", "headers": "{}", "body": "{}", "tray": True, "sound": True}

    def target_group(self) -> dict:
        item = self.rule_tree.currentItem()
        if item is None:
            return self.current_rule()
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node.get("type") == "condition" and item.parent() is not None:
            return item.parent().data(0, Qt.ItemDataRole.UserRole)
        return node if node.get("type") != "condition" else self.current_rule()

    def rule_tree_selection_changed(self) -> None:
        if self.rule_tree.currentItem() is None:
            return
        group = self.target_group()
        self.group_operator.blockSignals(True)
        self.group_operator.setCurrentIndex(max(0, self.group_operator.findData(group.get("operator", "and"))))
        self.group_operator.blockSignals(False)
        self.load_action(group)

    def load_action(self, group: dict) -> None:
        action = group.get("action", self.default_action())
        self.action_type.setCurrentText(action.get("method", "POST")); self.action_url.setText(action.get("url", "")); self.action_headers.setPlainText(action.get("headers", "{}")); self.action_body.setPlainText(action.get("body", "{}")); self.tray_action.setChecked(bool(action.get("tray", True))); self.sound_action.setChecked(bool(action.get("sound", True)))

    def remove_node(self, group: dict, node: dict) -> bool:
        for index, child in enumerate(group.get("items", [])):
            if child is node:
                group["items"].pop(index)
                return True
            if child.get("type") == "group" and self.remove_node(child, node):
                return True
        return False

    def validate_rule(self) -> None:
        rule = self.current_rule(); action = rule.get("action", {})
        errors = []
        if not rule.get("items"): errors.append("Додайте хоча б одну умову або вкладену групу.")
        for key in ("headers", "body"):
            try: json.loads(action.get(key, "{}"))
            except json.JSONDecodeError: errors.append(f"{key} має бути валідним JSON.")
        if action.get("url") and not action["url"].startswith(("https://", "http://")): errors.append("URL дії має починатися з http:// або https://.")
        QMessageBox.information(self, "Валідація правила", "Правило валідне." if not errors else "\n".join(errors))

    def show_technical_rule(self) -> None:
        QMessageBox.information(self, "Технічне правило", json.dumps(self.current_rule(), ensure_ascii=False, indent=2))

    def save_settings(self) -> None:
        self.repository.save_settings(self.settings_payload())
        QMessageBox.information(self, "Збережено", f"Налаштування збережено в {self.repository.settings_path}")

    def settings_payload(self) -> dict[str, str | int]:
        return {
            "api_port": self.api_port.value(),
            "language": str(self.language.currentData()),
            "telethon_api_id": self.telethon_api_id.text().strip(),
            "telethon_api_hash": self.telethon_api_hash.text().strip(),
            "telethon_phone": self.telethon_phone.text().strip(),
            "telethon_session_path": self.telethon_session_path.text().strip(),
        }

    def test_telethon(self) -> None:
        api_id_text = self.telethon_api_id.text().strip()
        api_hash = self.telethon_api_hash.text().strip()
        phone = self.telethon_phone.text().strip()
        if not api_id_text.isdigit() or not api_hash or not phone:
            self.telethon_status.setText("Заповніть коректні API ID, API Hash і номер телефону перед тестом.")
            return
        self.repository.save_settings(self.settings_payload())
        self.telethon_test.setEnabled(False)
        self.telethon_status.setText("Підключення до Telegram…")
        worker = TelethonAuthWorker(
            int(api_id_text), api_hash, phone, self.telethon_code.text().strip(), self.telethon_session_path.text().strip()
        )
        self.telethon_auth_workers.append(worker)
        worker.completed.connect(self.telethon_auth_finished)
        worker.failed.connect(self.telethon_auth_failed)
        worker.finished.connect(lambda: self.telethon_auth_workers.remove(worker) if worker in self.telethon_auth_workers else None)
        worker.start()

    def telethon_auth_finished(self, message: str) -> None:
        self.telethon_test.setEnabled(True)
        self.telethon_code.clear()
        self.telethon_status.setText(message)

    def telethon_auth_failed(self, message: str) -> None:
        self.telethon_test.setEnabled(True)
        self.telethon_status.setText(f"Помилка Telethon: {message}")


def run_ui(repository: StateRepository) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Telegram Alert Monitor")
    window = MainWindow(repository); window.show()
    return app.exec()
