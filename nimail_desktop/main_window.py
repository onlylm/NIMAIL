from __future__ import annotations

from functools import partial

from PySide6.QtCore import QSize, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QCompleter, QDialog, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QInputDialog, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import credential_store
from .api_client import ApiClient, ApiError, batch_txt_lines, normalize_server_url, validate_apple_cookie
from .config import ASSET_DIR
from .local_server import ensure_local_server, read_local_bootstrap_token
from .theme import DARK_STYLE, STYLE
from .worker import Worker


def run_async(owner, function, success, error=None, button=None):
    if button:
        button.setEnabled(False)
    worker = Worker(function)
    owner._workers.add(worker)

    def cleanup():
        owner._workers.discard(worker)
        if button:
            button.setEnabled(True)

    def ok(value):
        cleanup()
        success(value)

    def failed(message):
        cleanup()
        (error or owner.show_error)(message)

    worker.signals.success.connect(ok)
    worker.signals.error.connect(failed)
    QThreadPool.globalInstance().start(worker)


def card(layout=None):
    frame = QFrame()
    frame.setObjectName("card")
    frame.setLayout(layout or QVBoxLayout())
    frame.layout().setContentsMargins(20, 18, 20, 18)
    frame.layout().setSpacing(12)
    return frame


def button(text: str, kind: str = "secondary"):
    value = QPushButton(text)
    value.setObjectName(kind)
    value.setCursor(Qt.PointingHandCursor)
    return value


def page_header(title: str, subtitle: str):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 12)
    layout.setSpacing(3)
    heading = QLabel(title)
    heading.setObjectName("pageTitle")
    copy = QLabel(subtitle)
    copy.setObjectName("pageSub")
    layout.addWidget(heading)
    layout.addWidget(copy)
    return widget


def set_status_chip(label: QLabel, text: str, ok: bool):
    label.setText(("●  " if ok else "○  ") + text)
    label.setProperty("ok", "true" if ok else "false")
    label.style().unpolish(label)
    label.style().polish(label)


class DurationComboBox(QComboBox):
    """带常用期限和自定义入口的秒数选择器；None 表示长期有效。"""

    CUSTOM = "__custom__"
    UNITS = {"分钟": 60, "小时": 3600, "天": 86400}

    def __init__(self, long_text: str, default_seconds: int | None, include_minutes: bool = False):
        super().__init__()
        self._last_valid_index = 0
        self._custom_index = None
        self.addItem(long_text, None)
        self.addItem("7 天", 7 * 86400)
        self.addItem("3 天", 3 * 86400)
        self.addItem("1 天", 86400)
        if include_minutes:
            self.addItem("30 分钟", 30 * 60)
        self.addItem("自定义时长…", self.CUSTOM)
        matching = self.findData(default_seconds)
        if matching >= 0:
            self.setCurrentIndex(matching)
            self._last_valid_index = matching
        elif default_seconds is not None:
            self._insert_custom_value(default_seconds, self._format_seconds(default_seconds))
        self.currentIndexChanged.connect(self._selection_changed)

    @staticmethod
    def _format_seconds(seconds: int) -> str:
        if seconds % 86400 == 0:
            return f"{seconds // 86400} 天"
        if seconds % 3600 == 0:
            return f"{seconds // 3600} 小时"
        return f"{max(1, seconds // 60)} 分钟"

    def _insert_custom_value(self, seconds: int, label: str):
        self.blockSignals(True)
        if self._custom_index is not None:
            self.removeItem(self._custom_index)
        action_index = self.findData(self.CUSTOM)
        self.insertItem(action_index, f"自定义：{label}", seconds)
        self._custom_index = action_index
        self.setCurrentIndex(action_index)
        self._last_valid_index = action_index
        self.blockSignals(False)

    def _selection_changed(self, index: int):
        if self.itemData(index) != self.CUSTOM:
            self._last_valid_index = index
            return
        unit, accepted = QInputDialog.getItem(
            self, "自定义时长", "时间单位", list(self.UNITS), 1, False
        )
        if not accepted:
            self.setCurrentIndex(self._last_valid_index)
            return
        maximum = 3650 if unit == "天" else (87600 if unit == "小时" else 5256000)
        amount, accepted = QInputDialog.getInt(
            self, "自定义时长", f"请输入{unit}数", 1, 1, maximum, 1
        )
        if not accepted:
            self.setCurrentIndex(self._last_valid_index)
            return
        self._insert_custom_value(amount * self.UNITS[unit], f"{amount} {unit}")

    def seconds(self) -> int | None:
        value = self.currentData()
        return value if isinstance(value, int) else None


class LoginWidget(QWidget):
    authenticated = Signal(str, str, str)

    def __init__(self, saved: dict | None = None):
        super().__init__()
        self._workers = set()
        self.setObjectName("root")
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)
        panel = card()
        panel.setFixedWidth(430)
        logo = QLabel()
        pixmap = QPixmap(str(ASSET_DIR / "logo.png"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(74, 74, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo.setText("N")
            logo.setStyleSheet("font-size:42px;font-weight:900;color:#245fd8")
        logo.setAlignment(Qt.AlignCenter)
        title = QLabel("匿邮管理端")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:25px;font-weight:850")
        subtitle = QLabel("连接你的 NIMAIL 服务器")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setObjectName("pageSub")
        panel.layout().addWidget(logo)
        panel.layout().addWidget(title)
        panel.layout().addWidget(subtitle)

        form = QFormLayout()
        form.setSpacing(12)
        self.server = QLineEdit((saved or {}).get("server_url", "http://127.0.0.1:8788"))
        self.server.setPlaceholderText("https://mail.example.com")
        self.username = QLineEdit((saved or {}).get("username", ""))
        self.username.setPlaceholderText("首次创建至少 3 个字符")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("首次创建至少 12 个字符")
        form.addRow("服务器地址", self.server)
        form.addRow("管理员账号", self.username)
        form.addRow("管理员密码", self.password)
        panel.layout().addLayout(form)

        self.show_password = QCheckBox("显示密码")
        self.show_password.toggled.connect(
            lambda checked: self.password.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        panel.layout().addWidget(self.show_password, 0, Qt.AlignRight)

        self.setup_check = QCheckBox("首次安装：创建唯一管理员")
        panel.layout().addWidget(self.setup_check)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#b52c22")
        self.login_button = button("连接并登录", "primary")
        self.login_button.clicked.connect(self.submit)
        self.password.returnPressed.connect(self.submit)
        panel.layout().addWidget(self.error)
        panel.layout().addWidget(self.login_button)
        outer.addWidget(panel)

    def show_error(self, message: str):
        self.error.setText(message)

    def submit(self):
        self.error.clear()
        username = self.username.text().strip()
        password = self.password.text()
        if self.setup_check.isChecked():
            if len(username) < 3:
                return self.show_error("管理员账号至少需要 3 个字符，例如 lm-admin。")
            if len(password) < 12:
                return self.show_error("管理员密码至少需要 12 个字符，请组合字母、数字和符号。")

        def work():
            server_url = normalize_server_url(self.server.text())
            ensure_local_server(server_url)
            client = ApiClient(server_url)
            state = client.bootstrap_status()
            if state.get("required"):
                if not self.setup_check.isChecked():
                    raise ApiError("服务器尚未初始化，请勾选“首次安装：创建唯一管理员”。")
                client.bootstrap(read_local_bootstrap_token(server_url), username, password)
            result = client.login(username, password)
            return server_url, result["admin"]["username"], result["token"]

        run_async(self, work, lambda value: self.authenticated.emit(*value), button=self.login_button)


class AdminWidget(QWidget):
    logout_requested = Signal()

    def __init__(self, client: ApiClient, username: str):
        super().__init__()
        self.client, self.username = client, username
        self._workers = set()
        self.mailbox_items = []
        self.current_job_id = ""
        self.current_batch_job = None
        self.polling_batch = False
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.page_names = ["概览", "批量创建", "邮箱管理", "隐私收件箱", "服务器设置"]
        root.addWidget(self.build_sidebar())
        body = QWidget()
        body.setObjectName("appBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.build_topbar())
        self.pages = QStackedWidget()
        self.pages.setObjectName("content")
        # QStackedWidget 默认会用所有页面的最大最小宽度；邮箱工具栏不应把整个窗口撑宽。
        self.pages.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.pages.setMinimumWidth(0)
        self.pages.addWidget(self.build_dashboard())
        self.pages.addWidget(self.build_batch())
        self.pages.addWidget(self.build_mailboxes())
        self.pages.addWidget(self.build_inbox())
        self.pages.addWidget(self.build_settings())
        body_layout.addWidget(self.pages, 1)
        root.addWidget(body, 1)
        self.batch_timer = QTimer(self)
        self.batch_timer.setInterval(1500)
        self.batch_timer.timeout.connect(self.poll_batch)
        self.navigate(0)

    def show_error(self, message: str):
        QMessageBox.warning(self, "操作失败", message)

    def build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(208)
        self.sidebar = sidebar
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 16)
        layout.setSpacing(6)
        self.sidebar_layout = layout
        brand = QHBoxLayout()
        brand.setContentsMargins(10, 0, 0, 0)
        brand.setSpacing(11)
        logo = QLabel()
        pixmap = QPixmap(str(ASSET_DIR / "logo.png"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(42, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAccessibleName("匿邮图标")
        brand_copy = QWidget()
        brand_text = QVBoxLayout(brand_copy); brand_text.setContentsMargins(0, 0, 0, 0); brand_text.setSpacing(1)
        name = QLabel("匿邮")
        name.setObjectName("brandName")
        sub = QLabel("NIMAIL SERVER")
        sub.setObjectName("brandSub")
        brand_text.addWidget(name)
        brand_text.addWidget(sub)
        brand.addWidget(logo)
        brand.addWidget(brand_copy)
        self.brand_copy = brand_copy
        layout.addLayout(brand)
        layout.addSpacing(18)
        labels = [
            ("仪表盘", "服务器运行概览", "nav-dashboard.svg"),
            ("批量创建", "按数量自动生成", "nav-batch.svg"),
            ("邮箱管理", "邮箱与 CDK", "nav-mail.svg"),
            ("隐私收件箱", "主动查看邮件", "nav-inbox.svg"),
            ("服务器设置", "Apple 与 IMAP", "nav-settings.svg"),
        ]
        self.nav_buttons = []
        for index, (name_text, tip, icon_name) in enumerate(labels):
            nav = QPushButton(name_text)
            nav.setObjectName("navButton")
            nav.setCheckable(True)
            nav.setToolTip(f"{name_text}：{tip}")
            nav.setAccessibleName(name_text)
            nav.setProperty("fullText", name_text)
            nav.setIcon(QIcon(str(ASSET_DIR / icon_name)))
            nav.setIconSize(QSize(18, 18))
            nav.clicked.connect(partial(self.navigate, index))
            self.nav_buttons.append(nav)
            layout.addWidget(nav)
        layout.addStretch()
        user_row = QHBoxLayout()
        user_row.setContentsMargins(10, 10, 8, 0)
        avatar = QLabel((self.username[:2] or "管").upper())
        avatar.setObjectName("userAvatar"); avatar.setAlignment(Qt.AlignCenter)
        user_copy = QWidget()
        user_text = QVBoxLayout(user_copy); user_text.setContentsMargins(0, 0, 0, 0); user_text.setSpacing(1)
        user_name = QLabel(self.username); user_name.setObjectName("userName")
        user_role = QLabel("唯一管理员"); user_role.setObjectName("userRole")
        user_text.addWidget(user_name); user_text.addWidget(user_role)
        user_row.addWidget(avatar); user_row.addWidget(user_copy); user_row.addStretch()
        self.user_copy = user_copy
        layout.addLayout(user_row)
        return sidebar

    def build_topbar(self):
        topbar = QFrame(); topbar.setObjectName("topbar"); topbar.setFixedHeight(58)
        layout = QHBoxLayout(topbar); layout.setContentsMargins(22, 0, 22, 0); layout.setSpacing(16)
        title_box = QVBoxLayout(); title_box.setSpacing(0)
        self.topbar_title = QLabel("概览"); self.topbar_title.setObjectName("topbarTitle")
        subtitle = QLabel("服务器本机管理 · 公网仅开放 CDK 取信"); subtitle.setObjectName("topbarSub")
        self.topbar_subtitle = subtitle
        title_box.addWidget(self.topbar_title); title_box.addWidget(subtitle)
        layout.addLayout(title_box); layout.addStretch()
        self.server_chip = QLabel(); self.server_chip.setObjectName("topStatus")
        self.apple_chip = QLabel(); self.apple_chip.setObjectName("topStatus")
        self.imap_chip = QLabel(); self.imap_chip.setObjectName("topStatus")
        set_status_chip(self.server_chip, "服务器在线", True)
        set_status_chip(self.apple_chip, "Apple 未连接", False)
        set_status_chip(self.imap_chip, "IMAP 未配置", False)
        for item in (self.server_chip, self.apple_chip, self.imap_chip):
            layout.addWidget(item, 0, Qt.AlignVCenter)
        return topbar

    def resizeEvent(self, event):
        super().resizeEvent(event)
        collapsed = event.size().width() < 1060
        if getattr(self, "_sidebar_collapsed", None) == collapsed:
            return
        self._sidebar_collapsed = collapsed
        self.sidebar.setFixedWidth(68 if collapsed else 208)
        self.sidebar_layout.setContentsMargins(8 if collapsed else 12, 18, 8 if collapsed else 12, 16)
        self.brand_copy.setVisible(not collapsed)
        self.user_copy.setVisible(not collapsed)
        self.topbar_subtitle.setVisible(not collapsed)
        self.apple_chip.setVisible(not collapsed)
        self.imap_chip.setVisible(not collapsed)
        for nav in self.nav_buttons:
            nav.setText("" if collapsed else nav.property("fullText"))
            nav.setProperty("collapsed", "true" if collapsed else "false")
            nav.style().unpolish(nav)
            nav.style().polish(nav)
        if hasattr(self, "batch_form"):
            self.arrange_batch_form(collapsed)

    def page_container(self, title, subtitle, scrollable=False):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(22, 22, 22, 24)
        layout.setSpacing(20)
        layout.addWidget(page_header(title, subtitle))
        if not scrollable:
            return widget, layout
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(widget)
        return scroll, layout

    def navigate(self, index: int):
        self.pages.setCurrentIndex(index)
        self.topbar_title.setText(self.page_names[index])
        for i, nav in enumerate(self.nav_buttons):
            nav.setChecked(i == index)
        if index == 0:
            self.refresh_status()
        elif index == 1:
            self.load_latest_batch()
        elif index in (2, 3):
            self.refresh_mailboxes()

    def build_dashboard(self):
        page, layout = self.page_container("运行概览", "服务器运行状态与数据概览")
        grid = QGridLayout()
        self.stat_mailboxes = QLabel("—")
        self.stat_messages = QLabel("—")
        self.stat_imap = QLabel("—")
        self.stat_apple = QLabel("—")
        for index, (label, value) in enumerate([
            ("隐藏邮箱", self.stat_mailboxes), ("已归档邮件", self.stat_messages),
            ("IMAP 收信", self.stat_imap), ("Apple 会话", self.stat_apple),
        ]):
            box = card()
            value.setObjectName("statValue")
            caption = QLabel(label)
            caption.setObjectName("statLabel")
            box.layout().addWidget(value)
            box.layout().addWidget(caption)
            grid.addWidget(box, index // 2, index % 2)
        layout.addLayout(grid)
        self.status_detail = QLabel("正在连接服务器…")
        self.status_detail.setWordWrap(True)
        detail = card()
        detail.layout().addWidget(self.status_detail)
        refresh = button("刷新状态")
        refresh.clicked.connect(self.refresh_status)
        detail.layout().addWidget(refresh, 0, Qt.AlignLeft)
        layout.addWidget(detail)
        layout.addStretch()
        return page

    def refresh_status(self):
        def done(data):
            self.stat_mailboxes.setText(str(data["mailbox_count"]))
            self.stat_messages.setText(str(data["message_count"]))
            self.stat_imap.setText("已连接" if data["imap"]["configured"] else "未配置")
            self.stat_apple.setText("已连接" if data["apple"]["configured"] else "未配置")
            self.status_detail.setText(
                f"服务器 {data['version']} · {self.client.server_url}\n"
                f"最近收信：{data['imap']['last_sync'] or '尚未同步'}"
                + (f"\n错误：{data['imap']['last_error']}" if data["imap"]["last_error"] else "")
            )
            self.setting_status.setText(
                f"Apple：{'已连接' if data['apple']['configured'] else '未配置'}　"
                f"IMAP：{'已连接' if data['imap']['configured'] else '未配置'}"
            )
            deployment = data.get("deployment") or {"mode": "local", "domain": "", "viewer_base_url": ""}
            mode_name = "远程服务器" if deployment.get("mode") == "server" else "本机"
            domain = deployment.get("domain") or "未设置"
            viewer_base = deployment.get("viewer_base_url") or self.client.server_url
            self.deployment_status.setText(
                f"部署模式：{mode_name}　公网域名：{domain}\nCDK 链接前缀：{viewer_base}/c/"
            )
            if deployment.get("domain") and not self.public_domain.hasFocus():
                self.public_domain.setText(deployment["domain"])
            set_status_chip(self.server_chip, "服务器在线", True)
            set_status_chip(self.apple_chip, "Apple 已连接" if data["apple"]["configured"] else "Apple 未连接", data["apple"]["configured"])
            set_status_chip(self.imap_chip, "IMAP 运行中" if data["imap"]["configured"] else "IMAP 未配置", data["imap"]["configured"])
        run_async(self, self.client.status, done)

    def build_batch(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 22, 22, 24)
        layout.setSpacing(20)

        layout.addWidget(page_header(
            "创建隐藏邮箱", "完全随机 Apple 标签 · 独立 CDK · 按顺序安全创建"
        ))

        form_card = card()
        form = QGridLayout()
        form.setHorizontalSpacing(14); form.setVerticalSpacing(9)
        self.batch_count = QSpinBox(); self.batch_count.setRange(1, 20); self.batch_count.setValue(5)
        self.batch_count.setToolTip("建议每批 5 个；Apple 未公布固定数量上限")
        self.batch_prefix = QLineEdit("完全随机（每个邮箱独立生成）")
        self.batch_prefix.setReadOnly(True)
        self.batch_prefix.setToolTip("不使用连续编号、日期或批次前缀")
        self.batch_interval = QSpinBox(); self.batch_interval.setRange(5, 300); self.batch_interval.setValue(30); self.batch_interval.setSuffix(" 秒")
        self.batch_interval.setToolTip("建议 30～60 秒，降低触发 iCloud 临时频率控制的概率")
        self.deactivate_duration = DurationComboBox("长期有效", None, include_minutes=True)
        self.message_retention = DurationComboBox("长期保留", 7 * 86400)
        self.cdk_retention = DurationComboBox("长期有效", None)
        self.apple_action = QComboBox(); self.apple_action.addItem("到期停用隐藏邮箱", "deactivate"); self.apple_action.addItem("到期永久删除", "delete"); self.apple_action.addItem("不操作 Apple 邮箱", "keep")
        fields = [
            ("创建数量", self.batch_count), ("Apple 标签", self.batch_prefix),
            ("创建间隔", self.batch_interval), ("到期后的 Apple 操作", self.apple_action),
            ("首封邮件后邮箱有效期", self.deactivate_duration),
            ("首封邮件后邮件保留期", self.message_retention),
            ("首封邮件后 CDK 有效期", self.cdk_retention),
        ]
        self.batch_form = form
        self.batch_fields = []
        for text, widget in fields:
            label = QLabel(text); label.setObjectName("fieldLabel")
            widget.setMinimumWidth(120)
            self.batch_fields.append((label, widget))
        self.batch_start = button("开始自动创建", "primary")
        self.batch_start.setMinimumWidth(164); self.batch_start.setFixedHeight(48)
        self.batch_start.clicked.connect(self.start_batch)
        self.arrange_batch_form(False)
        form_card.layout().addLayout(form)
        policy_hint = QLabel("长期表示不自动到期；其他期限均从该隐藏邮箱收到第一封邮件时开始计算。")
        policy_hint.setObjectName("pageSub")
        form_card.layout().addWidget(policy_hint)
        layout.addWidget(form_card)

        progress_card = card()
        top = QHBoxLayout(); top.setSpacing(10)
        progress_title = QLabel("创建进度"); progress_title.setObjectName("sectionTitle")
        self.batch_fraction = QLabel("0 / 0"); self.batch_fraction.setObjectName("progressFraction")
        self.batch_state = QLabel("尚未开始"); self.batch_state.setObjectName("pageSub")
        top.addWidget(progress_title); top.addWidget(self.batch_fraction); top.addWidget(self.batch_state)
        top.addStretch()
        copy_cdk = button("复制 CDK"); copy_cdk.clicked.connect(self.copy_batch_cdk)
        export = button("⇩  导出 TXT"); export.clicked.connect(self.export_batch_results)
        top.addWidget(copy_cdk); top.addWidget(export)
        progress_card.layout().addLayout(top)

        progress_row = QHBoxLayout(); progress_row.setSpacing(16)
        self.batch_progress = QProgressBar(); self.batch_progress.setRange(0, 100); self.batch_progress.setTextVisible(False)
        self.batch_percent = QLabel("0%"); self.batch_percent.setObjectName("progressPercent")
        progress_row.addWidget(self.batch_progress, 1); progress_row.addWidget(self.batch_percent)
        progress_card.layout().addLayout(progress_row)
        self.batch_error = QLabel("")
        self.batch_error.setWordWrap(True)
        self.batch_error.setObjectName("batchError")
        self.batch_error.hide()
        progress_card.layout().addWidget(self.batch_error)
        self.batch_table = QTableWidget(0, 5)
        self.batch_table.setHorizontalHeaderLabels(["序号", "标签", "隐藏邮箱", "CDK", "状态"])
        header_view = self.batch_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Fixed); self.batch_table.setColumnWidth(0, 74)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.Stretch)
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)
        header_view.setSectionResizeMode(4, QHeaderView.Fixed); self.batch_table.setColumnWidth(4, 112)
        self.batch_table.verticalHeader().setVisible(False)
        self.batch_table.verticalHeader().setDefaultSectionSize(43)
        self.batch_table.setAlternatingRowColors(True)
        self.batch_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.batch_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.batch_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.batch_table.setShowGrid(False)
        progress_card.layout().addWidget(self.batch_table)
        layout.addWidget(progress_card, 1)
        return page

    def arrange_batch_form(self, compact: bool):
        columns = 2 if compact else 4
        for label, widget in self.batch_fields:
            self.batch_form.removeWidget(label)
            self.batch_form.removeWidget(widget)
        self.batch_form.removeWidget(self.batch_start)
        for column in range(4):
            self.batch_form.setColumnStretch(column, 1 if column < columns else 0)
        for index, (label, widget) in enumerate(self.batch_fields):
            widget.setMinimumWidth(120 if compact else 145)
            field_row, field_column = divmod(index, columns)
            grid_row = field_row * 2
            self.batch_form.addWidget(label, grid_row, field_column)
            self.batch_form.addWidget(widget, grid_row + 1, field_column)
        last_row = ((len(self.batch_fields) - 1) // columns) * 2
        self.batch_form.addWidget(self.batch_start, last_row, columns - 1, 2, 1, Qt.AlignBottom)

    def start_batch(self):
        payload = {
            "count": self.batch_count.value(), "label_prefix": "随机标签",
            "note": "由匿邮管理端批量创建", "interval_seconds": self.batch_interval.value(),
            "deactivate_after_seconds": self.deactivate_duration.seconds(),
            "message_retention_seconds": self.message_retention.seconds(),
            "cdk_retention_seconds": self.cdk_retention.seconds(),
            "apple_action": self.apple_action.currentData(),
        }

        def done(data):
            self.current_job_id = data["job"]["id"]
            self.render_batch(data["job"])
            self.batch_timer.start()
        run_async(self, lambda: self.client.start_batch(payload), done, button=self.batch_start)

    def load_latest_batch(self):
        run_async(self, self.client.latest_batch, lambda data: self.render_batch(data.get("job")) if data.get("job") else None)

    def poll_batch(self):
        if not self.current_job_id or self.polling_batch:
            return
        self.polling_batch = True
        def done(data):
            self.polling_batch = False
            job = data["job"]
            self.render_batch(job)
            if job["state"] not in ("queued", "running"):
                self.batch_timer.stop(); self.refresh_mailboxes()
        run_async(self, lambda: self.client.batch_status(self.current_job_id), done,
                  lambda message: (setattr(self, "polling_batch", False), self.show_error(message)))

    def render_batch(self, job):
        if not job:
            return
        self.current_batch_job = job
        self.current_job_id = job["id"]
        names = {"queued": "等待开始", "running": "正在自动创建", "completed": "创建完成", "failed": "任务已停止"}
        percent = round(job["completed_count"] / job["requested_count"] * 100)
        self.batch_state.setText(names.get(job["state"], job["state"]))
        self.batch_fraction.setText(f"{job['completed_count']} / {job['requested_count']}")
        self.batch_progress.setValue(percent)
        self.batch_percent.setText(f"{percent}%")
        error_message = (job.get("error") or "").strip()
        if job["state"] == "failed" and error_message:
            self.batch_error.setText(f"停止原因：{error_message}")
            self.batch_error.show()
        else:
            self.batch_error.clear()
            self.batch_error.hide()
        self.batch_table.setRowCount(len(job["items"]))
        state_names = {"waiting": "○  等待", "creating": "◌  创建中", "success": "●  已创建", "failed": "×  失败", "cancelled": "—  已取消"}
        state_colors = {"waiting": "#7b8799", "creating": "#2762e9", "success": "#1ca879", "failed": "#c23b32", "cancelled": "#7b8799"}
        for row, item in enumerate(job["items"]):
            values = [str(item["position"]), item["label"], item.get("address") or "—",
                      item.get("cdk") or "—", state_names.get(item["state"], item["state"])]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value); cell.setData(Qt.UserRole, item)
                if column == 4:
                    cell.setForeground(QBrush(QColor(state_colors.get(item["state"], "#34435a"))))
                self.batch_table.setItem(row, column, cell)
        if job["state"] in ("queued", "running"):
            self.batch_timer.start()

    def copy_batch_cdk(self):
        row = self.batch_table.currentRow()
        if row < 0:
            return self.show_error("请先选择一条成功记录")
        value = self.batch_table.item(row, 3).text()
        if value == "—":
            return self.show_error("该条记录尚未生成 CDK")
        QApplication.clipboard().setText(value)

    def export_batch_results(self):
        job = getattr(self, "current_batch_job", None)
        if not job:
            return self.show_error("当前没有可导出的批量创建结果")
        path, _filter = QFileDialog.getSaveFileName(
            self, "导出邮箱与取信链接", "NIMAIL-邮箱链接.txt", "文本文件 (*.txt)"
        )
        if not path:
            return
        lines = batch_txt_lines(job, self.client.server_url)
        if not lines:
            return self.show_error("当前批量任务中没有创建成功的邮箱")
        with open(path, "w", encoding="utf-8-sig", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
        QMessageBox.information(self, "导出完成", f"已导出 {len(lines)} 个邮箱：\n{path}")

    def build_mailboxes(self):
        page, layout = self.page_container("邮箱管理", "创建、复制、轮换和删除隐藏邮箱")
        tools = QHBoxLayout()
        refresh = button("刷新"); refresh.clicked.connect(self.refresh_mailboxes)
        copy = button("复制 CDK"); copy.clicked.connect(self.copy_selected_cdk)
        open_link = button("打开取信网址"); open_link.clicked.connect(self.open_selected_link)
        view = button("主动查看邮件"); view.clicked.connect(self.view_selected_mail)
        rotate = button("重新生成 CDK"); rotate.clicked.connect(self.rotate_selected_cdk)
        self.delete_mailbox_button = button("删除邮箱", "danger")
        self.delete_mailbox_button.clicked.connect(self.delete_selected_mailbox)
        remove = self.delete_mailbox_button
        for widget in (refresh, copy, open_link, view, rotate, remove): tools.addWidget(widget)
        tools.addStretch()
        self.mailbox_selection_count = QLabel("未选择邮箱")
        self.mailbox_selection_count.setObjectName("selectionCount")
        tools.addWidget(self.mailbox_selection_count)
        layout.addLayout(tools)
        self.mailbox_table = QTableWidget(0, 6)
        self.mailbox_table.setHorizontalHeaderLabels(["隐藏邮箱", "用途", "CDK", "邮件数", "状态", "首封邮件"])
        self.mailbox_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.mailbox_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.mailbox_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.mailbox_table.setAlternatingRowColors(True)
        self.mailbox_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mailbox_table.customContextMenuRequested.connect(self.show_mailbox_context_menu)
        self.mailbox_table.itemSelectionChanged.connect(self.update_mailbox_selection_count)
        self.mailbox_table.doubleClicked.connect(self.view_selected_mail)
        self.mailbox_table.setToolTip("支持 Ctrl/Shift 多选；右键可复制、查看、轮换或批量删除")
        layout.addWidget(self.mailbox_table, 1)
        return page

    def refresh_mailboxes(self):
        run_async(self, self.client.mailboxes, lambda data: self.render_mailboxes(data["items"]))

    def render_mailboxes(self, items):
        self.mailbox_items = items
        self.mailbox_table.setRowCount(len(items))
        self.inbox_combo.blockSignals(True); self.inbox_combo.clear()
        for row, item in enumerate(items):
            values = [item["address"], item["service_name"] or "—", item.get("cdk") or "已失效",
                      str(item["message_count"]), item["state"], item.get("first_message_at") or "—"]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value); cell.setData(Qt.UserRole, item["id"])
                self.mailbox_table.setItem(row, column, cell)
            self.inbox_combo.addItem(f"{item['service_name'] or '未命名'} · {item['address']}", item["id"])
        self.inbox_combo.blockSignals(False)
        self.reset_inbox_privacy()
        self.update_mailbox_selection_count()

    def selected_mailbox(self):
        items = self.selected_mailboxes()
        if not items:
            self.show_error("请先选择一个邮箱")
            return None
        if len(items) != 1:
            self.show_error("此操作一次只能处理一个邮箱")
            return None
        return items[0]

    def selected_mailboxes(self):
        rows = sorted({index.row() for index in self.mailbox_table.selectionModel().selectedRows()})
        return [self.mailbox_items[row] for row in rows if 0 <= row < len(self.mailbox_items)]

    def update_mailbox_selection_count(self):
        count = len(self.selected_mailboxes())
        self.mailbox_selection_count.setText(f"已选择 {count} 个邮箱" if count else "未选择邮箱")

    def copy_selected_cdk(self):
        items = self.selected_mailboxes()
        if not items:
            return self.show_error("请先选择邮箱")
        cdks = [item["cdk"] for item in items if item.get("cdk")]
        if not cdks:
            return self.show_error("选中的邮箱没有可用 CDK")
        QApplication.clipboard().setText("\n".join(cdks))

    def open_selected_link(self):
        item = self.selected_mailbox()
        if item and item.get("cdk"):
            QDesktopServices.openUrl(QUrl(f"{self.client.server_url}/c/{item['cdk']}"))

    def view_selected_mail(self):
        item = self.selected_mailbox()
        if not item: return
        self.navigate(3)
        index = self.inbox_combo.findData(item["id"])
        if index >= 0: self.inbox_combo.setCurrentIndex(index)
        self.load_inbox()

    def rotate_selected_cdk(self):
        item = self.selected_mailbox()
        if not item: return
        run_async(self, lambda: self.client.rotate_cdk(item["id"]),
                  lambda data: (QApplication.clipboard().setText(data["cdk"]), self.refresh_mailboxes()))

    def delete_selected_mailbox(self):
        items = self.selected_mailboxes()
        if not items:
            return self.show_error("请先选择一个或多个邮箱")
        apple_delete = self.choose_mailbox_delete_mode(items)
        if apple_delete is None:
            return

        def work():
            deleted, failed = [], []
            for item in items:
                try:
                    self.client.delete_mailbox(item["id"], apple_delete)
                    deleted.append(item)
                except Exception as exc:
                    failed.append((item, str(exc)))
            return {"deleted": deleted, "failed": failed, "apple_delete": apple_delete}

        run_async(self, work, self.mailboxes_deleted, button=self.delete_mailbox_button)

    def choose_mailbox_delete_mode(self, items):
        count = len(items)
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("删除邮箱")
        dialog.setText(f"准备删除选中的 {count} 个邮箱")
        dialog.setInformativeText("请选择删除方式。仅删除服务器记录不会影响 Apple 中的隐藏邮箱。")
        dialog.setDetailedText("\n".join(item["address"] for item in items))
        local_button = dialog.addButton("仅删除服务器记录", QMessageBox.AcceptRole)
        apple_button = dialog.addButton("同时从 Apple 永久删除", QMessageBox.DestructiveRole)
        dialog.addButton("取消", QMessageBox.RejectRole)
        dialog.setDefaultButton(local_button)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is local_button:
            return False
        if clicked is not apple_button:
            return None

        confirm = QMessageBox.warning(
            self,
            "确认永久删除",
            f"将从 Apple 永久删除 {count} 个隐藏邮箱，并清除服务器中的邮件与 CDK。\n此操作不可恢复，是否继续？",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return True if confirm == QMessageBox.Yes else None

    def mailboxes_deleted(self, result):
        deleted, failed = result["deleted"], result["failed"]
        self.refresh_mailboxes()
        if failed:
            details = "\n".join(f"{item['address']}：{error}" for item, error in failed)
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("批量删除完成")
            box.setText(f"成功删除 {len(deleted)} 个，失败 {len(failed)} 个")
            box.setDetailedText(details)
            box.exec()
        else:
            target = "Apple 和服务器" if result["apple_delete"] else "服务器"
            QMessageBox.information(self, "删除完成", f"已从{target}删除 {len(deleted)} 个邮箱。")

    def show_mailbox_context_menu(self, position):
        index = self.mailbox_table.indexAt(position)
        if not index.isValid():
            return
        selected_rows = {item.row() for item in self.mailbox_table.selectionModel().selectedRows()}
        if index.row() not in selected_rows:
            self.mailbox_table.clearSelection()
            self.mailbox_table.selectRow(index.row())

        count = len(self.selected_mailboxes())
        menu = QMenu(self)
        copy_action = menu.addAction("复制 CDK" if count == 1 else f"复制 {count} 个 CDK")
        view_action = menu.addAction("主动查看邮件")
        open_action = menu.addAction("打开取信网址")
        rotate_action = menu.addAction("重新生成 CDK")
        menu.addSeparator()
        delete_action = menu.addAction("删除邮箱…" if count == 1 else f"批量删除 {count} 个邮箱…")
        delete_action.setObjectName("destructiveAction")
        for action in (view_action, open_action, rotate_action):
            action.setEnabled(count == 1)

        chosen = menu.exec(self.mailbox_table.viewport().mapToGlobal(position))
        if chosen is copy_action:
            self.copy_selected_cdk()
        elif chosen is view_action:
            self.view_selected_mail()
        elif chosen is open_action:
            self.open_selected_link()
        elif chosen is rotate_action:
            self.rotate_selected_cdk()
        elif chosen is delete_action:
            self.delete_selected_mailbox()

    def build_inbox(self):
        page, layout = self.page_container("隐私收件箱", "后台默认不展示邮件，只有主动操作后才加载内容")
        privacy = QLabel("隐私模式已开启：未点击“查看邮件”前，不会显示标题、正文或验证码。")
        privacy.setObjectName("privacy"); privacy.setWordWrap(True); privacy.setContentsMargins(14, 12, 14, 12)
        layout.addWidget(privacy)
        tools = QHBoxLayout()
        self.inbox_combo = QComboBox()
        self.inbox_combo.setEditable(True)
        self.inbox_combo.setInsertPolicy(QComboBox.NoInsert)
        self.inbox_combo.setMaxVisibleItems(12)
        self.inbox_combo.lineEdit().setPlaceholderText("输入隐藏邮箱地址或标签筛选")
        self.inbox_combo.lineEdit().setClearButtonEnabled(True)
        inbox_completer = QCompleter(self.inbox_combo.model(), self.inbox_combo)
        inbox_completer.setCaseSensitivity(Qt.CaseInsensitive)
        inbox_completer.setFilterMode(Qt.MatchContains)
        inbox_completer.setCompletionMode(QCompleter.PopupCompletion)
        inbox_completer.setMaxVisibleItems(12)
        self.inbox_combo.setCompleter(inbox_completer)
        self.inbox_combo.currentIndexChanged.connect(self.reset_inbox_privacy)
        self.inbox_combo.lineEdit().textEdited.connect(lambda _text: self.reset_inbox_privacy())
        view = button("主动查看邮件", "primary"); view.clicked.connect(self.load_inbox)
        sync = button("同步后查看"); sync.clicked.connect(self.sync_and_load)
        tools.addWidget(self.inbox_combo, 1); tools.addWidget(view); tools.addWidget(sync)
        layout.addLayout(tools)
        self.inbox_privacy = QLabel("请选择邮箱并主动点击查看")
        self.inbox_privacy.setAlignment(Qt.AlignCenter)
        self.inbox_privacy.setMinimumHeight(120)
        self.inbox_privacy.setObjectName("card")
        layout.addWidget(self.inbox_privacy)
        self.inbox_content = QWidget(); content = QHBoxLayout(self.inbox_content); content.setContentsMargins(0,0,0,0)
        self.message_table = QTableWidget(0, 4)
        self.message_table.setHorizontalHeaderLabels(["发件人", "主题", "验证码", "时间"])
        self.message_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.message_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.message_table.itemSelectionChanged.connect(self.show_message_detail)
        self.message_items = []
        self.message_detail = QPlainTextEdit(); self.message_detail.setReadOnly(True); self.message_detail.setPlaceholderText("选择邮件查看正文")
        content.addWidget(self.message_table, 3); content.addWidget(self.message_detail, 2)
        self.inbox_content.hide(); layout.addWidget(self.inbox_content, 1)
        return page

    def reset_inbox_privacy(self):
        if not hasattr(self, "inbox_content"): return
        self.inbox_content.hide(); self.inbox_privacy.show(); self.message_detail.clear()

    def load_inbox(self):
        mailbox_id = self.resolve_inbox_mailbox_id()
        if not mailbox_id: return
        def done(data):
            self.message_items = data["items"]
            self.message_table.setRowCount(len(self.message_items))
            for row, item in enumerate(self.message_items):
                values = [item["sender"], item["subject"], item.get("otp_code") or "—", item["received_at"]]
                for column, value in enumerate(values): self.message_table.setItem(row, column, QTableWidgetItem(value))
            self.inbox_privacy.hide(); self.inbox_content.show()
        run_async(self, lambda: self.client.mailbox_messages(mailbox_id), done)

    def resolve_inbox_mailbox_id(self):
        current_index = self.inbox_combo.currentIndex()
        current_text = self.inbox_combo.currentText().strip()
        if current_index >= 0 and current_text.casefold() == self.inbox_combo.itemText(current_index).strip().casefold():
            mailbox_id = self.inbox_combo.itemData(current_index)
            if mailbox_id:
                return mailbox_id

        query = current_text.casefold()
        if not query:
            self.show_error("请先输入或选择一个邮箱")
            return None

        matches = [
            item for item in self.mailbox_items
            if query in (item.get("address") or "").casefold()
            or query in (item.get("service_name") or "").casefold()
        ]
        if len(matches) == 1:
            index = self.inbox_combo.findData(matches[0]["id"])
            if index >= 0:
                self.inbox_combo.setCurrentIndex(index)
            return matches[0]["id"]
        if len(matches) > 1:
            self.show_error("匹配到多个邮箱，请从下拉列表中选择具体邮箱")
        else:
            self.show_error("没有找到匹配的邮箱")
        return None

    def sync_and_load(self):
        run_async(self, self.client.sync_imap, lambda data: self.load_inbox())

    def show_message_detail(self):
        row = self.message_table.currentRow()
        if 0 <= row < len(self.message_items):
            item = self.message_items[row]
            code = f"\n\n验证码：{item['otp_code']}" if item.get("otp_code") else ""
            self.message_detail.setPlainText(f"{item['subject']}\n{item['sender']}\n{item['received_at']}{code}\n\n{item.get('body_text') or item.get('preview') or ''}")

    def build_settings(self):
        page, layout = self.page_container(
            "服务器设置", "配置 iCloud 收信和 Apple 隐藏邮箱会话", scrollable=True
        )

        status_card = card()
        self.setting_status = QLabel("正在读取状态…")
        status_card.layout().addWidget(QLabel(f"服务器：{self.client.server_url}"))
        status_card.layout().addWidget(self.setting_status)
        layout.addWidget(status_card)

        deployment_card = card()
        deployment_title = QLabel("公网域名与 CDK 链接"); deployment_title.setObjectName("sectionTitle")
        deployment_card.layout().addWidget(deployment_title)
        self.deployment_status = QLabel("正在读取部署模式…")
        self.deployment_status.setWordWrap(True)
        deployment_card.layout().addWidget(self.deployment_status)
        domain_row = QHBoxLayout(); domain_row.setSpacing(10)
        self.public_domain = QLineEdit()
        self.public_domain.setPlaceholderText("例如 mail.example.com（不要填写 http:// 或路径）")
        save_domain = button("保存并应用域名", "primary")
        save_domain.clicked.connect(lambda: run_async(
            self,
            lambda: self.client.configure_deployment(self.public_domain.text().strip()),
            self.deployment_saved,
            button=save_domain,
        ))
        domain_row.addWidget(self.public_domain, 1); domain_row.addWidget(save_domain)
        deployment_card.layout().addLayout(domain_row)
        self.deployment_result = QLabel("修改域名不会改变邮箱和 CDK，只会更新访问链接前缀。")
        self.deployment_result.setWordWrap(True); self.deployment_result.setObjectName("pageSub")
        deployment_card.layout().addWidget(self.deployment_result)
        layout.addWidget(deployment_card)

        imap_card = card()
        imap_title = QLabel("iCloud IMAP 收信"); imap_title.setObjectName("sectionTitle")
        imap_card.layout().addWidget(imap_title)
        form = QFormLayout(); form.setSpacing(12)
        self.imap_email = QLineEdit(); self.imap_email.setPlaceholderText("name@icloud.com")
        self.imap_password = QLineEdit(); self.imap_password.setEchoMode(QLineEdit.Password)
        self.imap_password.setPlaceholderText("Apple 应用专用密码")
        form.addRow("iCloud 邮箱", self.imap_email)
        form.addRow("应用专用密码", self.imap_password)
        imap_card.layout().addLayout(form)
        imap_tools = QHBoxLayout()
        show_imap_password = QCheckBox("显示应用专用密码")
        show_imap_password.toggled.connect(
            lambda checked: self.imap_password.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        save_imap = button("保存并测试 IMAP", "primary")
        save_imap.clicked.connect(lambda: run_async(
            self,
            lambda: self.client.configure_imap(self.imap_email.text(), self.imap_password.text()),
            lambda _data: (self.imap_password.clear(), self.refresh_status()),
            button=save_imap,
        ))
        imap_tools.addWidget(save_imap); imap_tools.addWidget(show_imap_password); imap_tools.addStretch()
        imap_card.layout().addLayout(imap_tools)
        layout.addWidget(imap_card)

        apple_card = card()
        apple_title = QLabel("Apple 隐藏邮箱管理会话"); apple_title.setObjectName("sectionTitle")
        apple_card.layout().addWidget(apple_title)
        note = QLabel("使用电脑的默认浏览器登录 iCloud，然后把完整 Cookie 粘贴到下方。Cookie 只会发送到你的 NIMAIL 服务器，并使用 Windows DPAPI 加密保存。")
        note.setWordWrap(True); note.setObjectName("notice")
        apple_card.layout().addWidget(note)

        browser_row = QHBoxLayout()
        self.apple_region = QComboBox(); self.apple_region.addItem("中国大陆 iCloud", "china"); self.apple_region.addItem("全球 iCloud", "global")
        open_browser = button("1. 在默认浏览器打开 iCloud")
        open_browser.clicked.connect(self.open_default_icloud)
        browser_row.addWidget(self.apple_region, 1); browser_row.addWidget(open_browser); browser_row.addStretch()
        apple_card.layout().addLayout(browser_row)

        manual_label = QLabel("2. 手动粘贴完整 Cookie"); manual_label.setObjectName("fieldLabel")
        apple_card.layout().addWidget(manual_label)
        self.manual_cookie = QPlainTextEdit()
        self.manual_cookie.setObjectName("manualCookie")
        self.manual_cookie.setPlaceholderText("例如：X-APPLE-WEBAUTH-USER=...; X-APPLE-WEBAUTH-TOKEN=...; ...")
        self.manual_cookie.setFixedHeight(92)
        apple_card.layout().addWidget(self.manual_cookie)
        cookie_tools = QHBoxLayout()
        save_cookie = button("验证并加密保存 Cookie", "primary")
        save_cookie.clicked.connect(lambda: run_async(self, self.configure_manual_cookie, self.cookie_saved, button=save_cookie))
        self.cookie_result = QLabel(""); self.cookie_result.setObjectName("cookieSuccess")
        cookie_tools.addWidget(save_cookie); cookie_tools.addWidget(self.cookie_result); cookie_tools.addStretch()
        apple_card.layout().addLayout(cookie_tools)
        layout.addWidget(apple_card)

        logout = button("退出当前管理员", "danger")
        logout.clicked.connect(self.logout_requested.emit)
        layout.addWidget(logout, 0, Qt.AlignLeft)
        layout.addStretch()
        return page

    def open_default_icloud(self):
        url = "https://www.icloud.com.cn/icloudplus/" if self.apple_region.currentData() == "china" else "https://www.icloud.com/icloudplus/"
        if not QDesktopServices.openUrl(QUrl(url)):
            self.show_error("无法调用系统默认浏览器，请检查 Windows 默认浏览器设置")

    def deployment_saved(self, data):
        warning = data.get("warning") or ""
        if warning:
            self.deployment_result.setText(warning)
            QMessageBox.information(self, "域名已保存", warning)
        else:
            self.deployment_result.setText(
                f"已应用：https://{data['domain']}/c/CDK（新旧 CDK 均可使用）"
            )
        self.refresh_status()

    def configure_manual_cookie(self):
        cookie = validate_apple_cookie(self.manual_cookie.toPlainText())
        return self.client.configure_apple(cookie, self.apple_region.currentData())

    def cookie_saved(self, data):
        self.manual_cookie.clear()
        self.cookie_result.setText(f"已连接，检测到 {data.get('alias_count', 0)} 个隐藏邮箱")
        self.refresh_status()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._workers = set()
        self.setWindowTitle("匿邮管理端")
        self.setMinimumSize(820, 620)
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.resize(
                min(1320, max(820, available.width() - 64)),
                min(840, max(620, available.height() - 64)),
            )
        else:
            self.resize(1280, 800)
        self.apply_color_scheme()
        color_scheme_changed = getattr(QApplication.styleHints(), "colorSchemeChanged", None)
        if color_scheme_changed:
            color_scheme_changed.connect(self.apply_color_scheme)
        icon = QIcon(str(ASSET_DIR / "logo.png"))
        if not icon.isNull(): self.setWindowIcon(icon)
        self.stack = QStackedWidget(); self.setCentralWidget(self.stack)
        self.login_widget = None; self.admin_widget = None
        self.show_login(credential_store.load())
        saved = credential_store.load()
        if saved.get("token") and saved.get("server_url"):
            QTimer.singleShot(100, lambda: self.restore_session(saved))

    def apply_color_scheme(self, *_args):
        is_dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        self.setStyleSheet(STYLE + (DARK_STYLE if is_dark else ""))

    def show_error(self, message):
        QMessageBox.warning(self, "连接失败", message)

    def show_login(self, saved=None):
        login = LoginWidget(saved)
        login.authenticated.connect(self.open_admin)
        self.stack.addWidget(login); self.stack.setCurrentWidget(login)
        if self.login_widget: self.stack.removeWidget(self.login_widget); self.login_widget.deleteLater()
        self.login_widget = login

    def restore_session(self, saved):
        client = ApiClient(saved["server_url"], saved["token"])
        def restore():
            ensure_local_server(saved["server_url"])
            return client.status()
        run_async(self, restore,
                  lambda data: self.open_admin(saved["server_url"], saved.get("username") or data["admin"]["username"], saved["token"]),
                  lambda message: None)

    def open_admin(self, server_url: str, username: str, token: str):
        credential_store.save(server_url, username, token)
        client = ApiClient(server_url, token)
        admin = AdminWidget(client, username)
        admin.logout_requested.connect(self.logout)
        self.stack.addWidget(admin); self.stack.setCurrentWidget(admin)
        if self.admin_widget: self.stack.removeWidget(self.admin_widget); self.admin_widget.deleteLater()
        self.admin_widget = admin
        admin.refresh_status(); admin.refresh_mailboxes()

    def logout(self):
        credential_store.clear()
        self.show_login({"server_url": self.admin_widget.client.server_url, "username": self.admin_widget.username})
