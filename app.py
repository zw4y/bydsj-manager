"""捕鱼大世界 - 卡密授权版多账户资源查询工具。"""

import os
import hashlib
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QProxyStyle,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scripts.account_import import (
    build_tsv,
    filter_duplicate_accounts,
    parse_account_rows,
    paste_target_rows,
)
from scripts.account_search import find_account_rows, format_search_log
from scripts import (
    bydsj_client,
    gaia_login,
    query_service,
    security_center,
    warehouse,
    welfare,
)
from scripts.card_auth import (
    CardAuthClient,
    CardAuthError,
    derive_key,
    machine_id,
    mask_card_key,
    profile_dir,
)
from scripts.heartbeat import HeartbeatPolicy
from scripts.local_store import LocalAccountStore
from scripts.password_utils import generate_password, validate_password
from scripts.proxy_pool import (
    ProxyPool,
    fetch_proxies,
    load_proxy_config,
    mask_proxy,
    save_proxy_config,
)
from scripts.warehouse import deal_max_display, display_to_deal_num, display_unit

# 【部署配置】服务器地址内置，登录界面不展示；更换服务器时修改此处后重新打包/热更新
DEFAULT_SERVER_URL = "http://47.100.188.139:18432"
APP_VERSION = "1.0.2"

# 【美化新增-浅色Fluent】全局主题样式
THEME_QSS = """
QMainWindow, QDialog {
    background-color: #F3F3F3;
}
QWidget {
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei";
    color: #1B1B1B;
}
QLabel {
    background: transparent;
    color: #1B1B1B;
}
#resourcePanel, #accountPanel {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
}
QPushButton {
    background-color: #FFFFFF;
    color: #1B1B1B;
    border: 1px solid #D0D0D0;
    border-radius: 6px;
    padding: 5px 14px;
}
QPushButton:hover {
    background-color: #F0F6FC;
    border-color: #0078D4;
    color: #0078D4;
}
QPushButton:pressed {
    background-color: #E5F1FB;
}
QPushButton:disabled {
    background-color: #F5F5F5;
    color: #BDBDBD;
    border-color: #E8E8E8;
}
#tabButton:checked {
    background-color: #E5F1FB;
    border-color: #0078D4;
    color: #0078D4;
    font-weight: 600;
}
QLineEdit, QSpinBox {
    background-color: #FFFFFF;
    border: 1px solid #D0D0D0;
    border-radius: 6px;
    padding: 4px 8px;
    color: #1B1B1B;
    selection-background-color: #E5F1FB;
    selection-color: #1B1B1B;
}
QLineEdit:hover, QSpinBox:hover {
    border-color: #0078D4;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #0078D4;
}
QLineEdit:disabled, QSpinBox:disabled {
    background-color: #F5F5F5;
    color: #BDBDBD;
}
QSpinBox#plainSpin::up-button, QSpinBox#plainSpin::down-button {
    width: 0;
    height: 0;
    border: none;
    background: transparent;
}
QCheckBox, QRadioButton {
    color: #1B1B1B;
    spacing: 6px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #B0B0B0;
    background-color: #FFFFFF;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #0078D4;
}
QCheckBox::indicator:checked {
    background-color: #0078D4;
    border-color: #0078D4;
}
QRadioButton::indicator {
    border-radius: 8px;
}
QRadioButton::indicator:checked {
    background-color: #0078D4;
    border: 4px solid #FFFFFF;
}
QCheckBox:disabled, QRadioButton:disabled {
    color: #BDBDBD;
}
#accountTable {
    background-color: #FFFFFF;
    alternate-background-color: #FAFAFA;
    border: 1px solid #E0E0E0;
    gridline-color: #EFEFEF;
    selection-background-color: #E5F1FB;
    selection-color: #1B1B1B;
}
#accountTable QHeaderView::section {
    background-color: #F9F9F9;
    color: #616161;
    border: none;
    border-bottom: 1px solid #E0E0E0;
    border-right: 1px solid #E0E0E0;
    padding: 6px 4px;
    font-weight: 600;
    text-align: center;
}
#accountTable QTableCornerButton::section {
    background-color: #F9F9F9;
    border: none;
}
#iconCard {
    background-color: #F9F9F9;
    border: 1px solid #EDEDED;
    border-radius: 6px;
}
#iconCard:hover {
    background-color: #F0F6FC;
    border-color: #B8D8F7;
}
#iconLabel {
    background: transparent;
}
#qtyLabel {
    color: #616161;
}
#logArea {
    background-color: #FAFAFA;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
    padding: 6px;
    color: #1B1B1B;
    selection-background-color: #E5F1FB;
    selection-color: #1B1B1B;
}
#statusLabel {
    color: #616161;
    padding: 2px 4px;
}
QMenu {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 18px;
    border-radius: 4px;
    color: #1B1B1B;
}
QMenu::item:selected {
    background-color: #F0F6FC;
    color: #0078D4;
}
QMenu::separator {
    height: 1px;
    background: #E0E0E0;
    margin: 4px 6px;
}
QToolTip {
    background-color: #FFFFFF;
    color: #1B1B1B;
    border: 1px solid #E0E0E0;
    padding: 4px 8px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #C8C8C8;
    border-radius: 5px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #A8A8A8;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
}
QScrollBar::handle:horizontal {
    background: #C8C8C8;
    border-radius: 5px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #A8A8A8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
"""


class ActivationThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, server_url: str, card_key: str):
        super().__init__()
        self._server_url = server_url
        self._card_key = card_key

    def run(self):
        try:
            machine = machine_id()
            CardAuthClient(self._server_url).activate(self._card_key, machine)
            directory = profile_dir(self._card_key)
            directory.mkdir(parents=True, exist_ok=True)
            salt_path = directory / "salt.bin"
            if salt_path.exists():
                salt = salt_path.read_bytes()
            else:
                salt = os.urandom(16)
                salt_path.write_bytes(salt)
            key = derive_key(self._card_key, machine, salt)
            store = LocalAccountStore(str(directory / "accounts.db"), key)
            self.done.emit((store, self._server_url, self._card_key))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ActivationDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("卡密激活")
        self.setMinimumWidth(420)
        self.store = None
        self.card_key = ""
        self.server_url = DEFAULT_SERVER_URL

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.edt_key = QLineEdit()
        self.edt_key.setPlaceholderText("请输入卡密 BYDSJ-XXXX-XXXX-XXXX-XXXX")
        form.addRow("卡密", self.edt_key)
        layout.addLayout(form)

        self.btn_activate = QPushButton("激活并进入")
        self.btn_activate.clicked.connect(self._on_activate)
        layout.addWidget(self.btn_activate)
        self.lbl_status = QLabel("")
        layout.addWidget(self.lbl_status)

    def _on_activate(self):
        server_url = self.server_url.rstrip("/")
        card_key = self.edt_key.text().strip()
        if not card_key:
            QMessageBox.warning(self, "提示", "请输入卡密")
            return
        self.btn_activate.setEnabled(False)
        self.lbl_status.setText("正在联网校验卡密...")
        self._thread = ActivationThread(server_url, card_key)
        self._thread.done.connect(self._on_done)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_done(self, payload):
        self.store, self.server_url, self.card_key = payload
        self.accept()

    def _on_failed(self, message: str):
        self.btn_activate.setEnabled(True)
        self.lbl_status.setText("激活失败")
        QMessageBox.critical(self, "激活失败", message)


class HeartbeatThread(QThread):
    ok = Signal()
    rejected = Signal(str)
    network_error = Signal(str)
    locked = Signal(str)

    def __init__(
        self,
        server_url: str,
        card_key: str,
        interval_seconds: int = 1800,
        grace_seconds: int = 600,
        retry_interval_seconds: int = 60,
        client: CardAuthClient | None = None,
    ):
        super().__init__()
        self._client = client or CardAuthClient(server_url)
        self._card_key = card_key
        self._machine = machine_id()
        self._policy = HeartbeatPolicy(interval_seconds, grace_seconds)
        self._retry_interval = retry_interval_seconds
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        while not self._stop:
            wait_seconds = (
                self._retry_interval
                if self._policy.consecutive_failures > 0
                else self._policy.interval_seconds
            )
            if not self._sleep(wait_seconds):
                break
            try:
                self._client.validate(self._card_key, self._machine)
                self._policy.record_success()
                self.ok.emit()
            except CardAuthError as exc:
                self.rejected.emit(str(exc))
                break
            except Exception as exc:  # noqa: BLE001
                self._policy.record_failure()
                if self._policy.should_lock():
                    self.locked.emit(str(exc))
                    break
                self.network_error.emit(str(exc))

    def _sleep(self, seconds: float) -> bool:
        waited = 0.0
        while waited < seconds and not self._stop:
            time.sleep(min(1.0, seconds - waited))
            waited += min(1.0, seconds - waited)
        return not self._stop


class AccountDataThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        account: str,
        password: str,
        device_code: str | None = None,
        proxy: str | None = None,
        delay: float = 0,
    ):
        super().__init__()
        self._account = account
        self._password = password
        self._device_code = device_code
        self._proxy = proxy
        self._delay = delay

    def run(self):
        try:
            if self._delay > 0:
                time.sleep(self._delay)
            session = security_center.get_session(
                self._account, self._password, self._device_code, self._proxy
            )
            bag = bydsj_client.get_bag(
                session["user_id"], session["token"], self._proxy
            )
            repo = warehouse.get_repo(
                session["user_id"], session["token"], proxy=self._proxy
            )
            items = {pid: bag.get(pid, 0) for pid, _ in bydsj_client.ITEMS}
            result = {
                "account": self._account,
                "user_id": session["user_id"],
                "nickname": session.get("nickname") or "",
                "money": session.get("money", 0),
                "diamond": session.get("diamond", 0),
                "mobile": session.get("mobile") or "",
                "device_code": session.get("device_code") or "",
                "total_infull_num": session.get("total_infull_num", 0),
                "cannon": session.get("cannon", 0),
                "items": items,
                "repo": repo,
            }
            self.done.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class TrustCheckThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        account: str,
        password: str,
        device_code: str | None = None,
        proxy: str | None = None,
    ):
        super().__init__()
        self._account = account
        self._password = password
        self._device_code = device_code
        self._proxy = proxy

    def run(self):
        try:
            session = security_center.get_session(
                self._account, self._password, self._device_code, self._proxy
            )
            trusted = security_center.check_trust(
                session, proxy=self._proxy
            ).get("ifOpen") == 1
            self.done.emit((session, trusted))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class TrustActionThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        action: str,
        session: dict,
        phone: str,
        code: str = "",
        proxy: str | None = None,
    ):
        super().__init__()
        self._action = action
        self._session = session
        self._phone = phone
        self._code = code
        self._proxy = proxy

    def run(self):
        try:
            if self._action == "send":
                result = security_center.send_trust_sms(
                    self._session, self._phone, self._proxy
                )
            else:
                result = security_center.trust_device(
                    self._session,
                    self._phone,
                    self._session.get("device_code"),
                    self._code,
                    self._proxy,
                )
            self.done.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class GaiaLoginThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(
        self, account: str, password: str, proxy: str | None = None
    ):
        super().__init__()
        self._account = account
        self._password = password
        self._proxy = proxy

    def run(self):
        try:
            self.done.emit(
                gaia_login.login_user(self._account, self._password, self._proxy)
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class SendGaiaPwdCodeThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(
        self, login_info: dict, phone: str, proxy: str | None = None
    ):
        super().__init__()
        self._login_info = login_info
        self._phone = phone
        self._proxy = proxy

    def run(self):
        try:
            self.done.emit(
                gaia_login.gaia_send_update_pwd_code(
                    self._login_info["openId"],
                    self._login_info["openToken"],
                    self._phone,
                    self._proxy,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class DashijieSessionThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        account: str,
        password: str,
        device_code: str | None = None,
        proxy: str | None = None,
        require_device: bool = True,
    ):
        super().__init__()
        self._account = account
        self._password = password
        self._device_code = device_code
        self._proxy = proxy
        self._require_device = require_device

    def run(self):
        try:
            self.done.emit(
                security_center.get_session(
                    self._account,
                    self._password,
                    self._device_code,
                    self._proxy,
                    require_device=self._require_device,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class SendWebPwdCodeThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(
        self, session: dict, phone: str, proxy: str | None = None
    ):
        super().__init__()
        self._session = session
        self._phone = phone
        self._proxy = proxy

    def run(self):
        try:
            self.done.emit(
                security_center.send_change_pwd_sms(
                    self._session, self._phone, self._proxy
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ChangePasswordThread(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        login_info: dict,
        old_password: str,
        new_password: str,
        code: str,
        proxy: str | None = None,
    ):
        super().__init__()
        self._login_info = login_info
        self._old_password = old_password
        self._new_password = new_password
        self._code = code
        self._proxy = proxy

    def run(self):
        try:
            gaia_login.gaia_edit_password(
                self._login_info["openId"],
                self._login_info["openToken"],
                self._old_password,
                self._new_password,
                self._code,
                self._proxy,
            )
            self.done.emit(self._new_password)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class WebChangePasswordThread(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        session: dict,
        phone: str,
        code: str,
        new_password: str,
        proxy: str | None = None,
    ):
        super().__init__()
        self._session = session
        self._phone = phone
        self._code = code
        self._new_password = new_password
        self._proxy = proxy

    def run(self):
        try:
            security_center.change_password(
                self._session,
                self._phone,
                self._code,
                self._new_password,
                self._proxy,
            )
            self.done.emit(self._new_password)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class WarehouseDealThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        session: dict,
        prop_id: int,
        deal_num: int,
        secondary_password: str,
        proxy: str | None = None,
    ):
        super().__init__()
        self._session = session
        self._prop_id = prop_id
        self._deal_num = deal_num
        self._secondary_password = secondary_password
        self._proxy = proxy

    def run(self):
        try:
            result = warehouse.repo_deal(
                self._session["user_id"],
                self._session["token"],
                self._prop_id,
                self._deal_num,
                self._secondary_password,
                proxy=self._proxy,
            )
            if result.get("result") != 0:
                raise RuntimeError(result.get("msgText") or f"存取失败 result={result.get('result')}")
            self.done.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ProxyTestThread(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, api_url: str):
        super().__init__()
        self._api_url = api_url

    def run(self):
        try:
            entries = fetch_proxies(self._api_url)
            lines = [
                f"{e['host']} 到期:{datetime.fromtimestamp(e['deadline_ts']):%H:%M:%S}"
                for e in entries
            ]
            self.done.emit("\n".join(lines))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class UpdateCheckThread(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, server_url: str):
        super().__init__()
        self._server_url = server_url.rstrip("/")

    def run(self):
        try:
            resp = httpx.get(
                self._server_url + "/api/client/version",
                timeout=10,
                trust_env=False,
            )
            if resp.status_code == 404:
                raise RuntimeError("暂无更新")
            resp.raise_for_status()
            self.done.emit(resp.json())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class UpdateDownloadThread(QThread):
    progress = Signal(int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, target_path: str):
        super().__init__()
        self._url = url
        self._target_path = target_path

    def run(self):
        try:
            Path(self._target_path).parent.mkdir(parents=True, exist_ok=True)
            with httpx.stream(
                "GET", self._url, timeout=120, trust_env=False, follow_redirects=True
            ) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0) or 0)
                downloaded = 0
                with open(self._target_path, "wb") as f:
                    for chunk in resp.iter_bytes(1024 * 256):
                        if self.isInterruptionRequested():
                            raise RuntimeError("下载已取消")
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            self.progress.emit(int(downloaded * 100 / total))
            self.done.emit(self._target_path)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class BatchRefreshWorker(QThread):
    done = Signal(int, str, object)  # account_id, account, result
    failed = Signal(str, str, str)
    status = Signal(str)
    finished_all = Signal()

    def __init__(
        self,
        accounts: list[dict],
        pool: ProxyPool,
        delay_min: int,
        delay_max: int,
        enabled: bool,
    ):
        super().__init__()
        self._accounts = accounts
        self._pool = pool
        self._delay_min = delay_min
        self._delay_max = delay_max
        self._enabled = enabled
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def _query(self, account: dict, proxy: str | None) -> dict:
        session = security_center.get_session(
            account["account"],
            account["password"],
            account["device_code"] or None,
            proxy,
        )
        bag = bydsj_client.get_bag(
            session["user_id"], session["token"], proxy
        )
        repo = warehouse.get_repo(
            session["user_id"], session["token"], proxy=proxy
        )
        items = {pid: bag.get(pid, 0) for pid, _ in bydsj_client.ITEMS}
        return {
            "account": account["account"],
            "user_id": session["user_id"],
            "nickname": session.get("nickname") or "",
            "money": session.get("money", 0),
            "diamond": session.get("diamond", 0),
            "mobile": session.get("mobile") or "",
            "device_code": session.get("device_code") or "",
            "total_infull_num": session.get("total_infull_num", 0),
            "cannon": session.get("cannon", 0),
            "items": items,
            "repo": repo,
        }

    def run(self):
        total = len(self._accounts)
        for index, account in enumerate(self._accounts):
            if self._stop:
                break
            if index > 0 and self._delay_max > 0:
                delay = random.uniform(self._delay_min, self._delay_max)
                self.status.emit(f"等待 {delay:.0f} 秒后刷新下一个账号...")
                waited = 0.0
                while waited < delay and not self._stop:
                    time.sleep(min(1.0, delay - waited))
                    waited += min(1.0, delay - waited)
            if self._stop:
                break
            self.status.emit(
                f"正在刷新 {account['account']} ({index + 1}/{total}) ..."
            )
            proxy = None
            if self._enabled:
                proxy = self._pool.next()
                if proxy:
                    self.status.emit(f"使用代理 {self._pool.mask(proxy)}")
                else:
                    self.failed.emit(
                        account["account"],
                        self._pool.last_error or "代理获取失败",
                        "",
                    )
                    continue
            try:
                result = self._query(account, proxy)
                self.done.emit(account["id"], account["account"], result)
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                if proxy:
                    self._pool.mark_failed(proxy)
                    retry_proxy = self._pool.next()
                    if retry_proxy:
                        try:
                            result = self._query(account, retry_proxy)
                            self.done.emit(
                                account["id"], account["account"], result
                            )
                            continue
                        except Exception as exc2:  # noqa: BLE001
                            message = str(exc2)
                self.failed.emit(account["account"], message, proxy or "")
        self.finished_all.emit()


class WelfareWorker(QThread):
    """批量领取福利：每个账号登录后领取，成功后由界面取消勾选。"""

    done = Signal(int, str, str, object)  # account_id, account, kind, result
    failed = Signal(str, str, str)  # account, message, proxy
    status = Signal(str)
    finished_all = Signal()

    def __init__(
        self,
        accounts: list[dict],
        pool: ProxyPool,
        delay_min: int,
        delay_max: int,
        enabled: bool,
        kind: str,
    ):
        super().__init__()
        self._accounts = accounts
        self._pool = pool
        self._delay_min = delay_min
        self._delay_max = delay_max
        self._enabled = enabled
        self._kind = kind
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def _claim(self, account: dict, proxy: str | None) -> dict:
        session = security_center.get_session(
            account["account"],
            account["password"],
            account["device_code"] or None,
            proxy,
        )
        uid, token = session["user_id"], session["token"]
        if self._kind == "vip_daily":
            return welfare.claim_vip_daily(uid, token, proxy)
        return welfare.claim_thanksgiving_full(uid, token, proxy)

    def run(self):
        total = len(self._accounts)
        for index, account in enumerate(self._accounts):
            if self._stop:
                break
            if index > 0 and self._delay_max > 0:
                delay = random.uniform(self._delay_min, self._delay_max)
                self.status.emit(f"等待 {delay:.0f} 秒后领取下一个账号...")
                waited = 0.0
                while waited < delay and not self._stop:
                    time.sleep(min(1.0, delay - waited))
                    waited += min(1.0, delay - waited)
            if self._stop:
                break
            self.status.emit(
                f"正在领取 {account['account']} ({index + 1}/{total}) ..."
            )
            proxy = None
            if self._enabled:
                proxy = self._pool.next()
                if proxy:
                    self.status.emit(f"使用代理 {self._pool.mask(proxy)}")
                else:
                    self.failed.emit(
                        account["account"],
                        self._pool.last_error or "代理获取失败",
                        "",
                    )
                    continue
            try:
                result = self._claim(account, proxy)
                self.done.emit(account["id"], account["account"], self._kind, result)
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                if proxy:
                    self._pool.mark_failed(proxy)
                    retry_proxy = self._pool.next()
                    if retry_proxy:
                        try:
                            result = self._claim(account, retry_proxy)
                            self.done.emit(
                                account["id"], account["account"], self._kind, result
                            )
                            continue
                        except Exception as exc2:  # noqa: BLE001
                            message = str(exc2)
                self.failed.emit(account["account"], message, proxy or "")
        self.finished_all.emit()


class QuantityDialog(QDialog):
    def __init__(
        self,
        title: str,
        maximum: int,
        unit: str = "个",
        available: int | None = None,
    ):
        super().__init__()
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        if available is None:
            available = maximum
        layout.addWidget(QLabel(f"可用数量：{available} {unit}"))
        self.spin = QSpinBox()
        self.spin.setRange(1, max(1, maximum))
        self.spin.setValue(1)
        self.spin.setMinimumWidth(240)
        self.spin.setFixedHeight(42)
        self.spin.setStyleSheet("font-size: 18px;")
        layout.addWidget(self.spin)
        btn = QPushButton("确定")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


class EditAccountDialog(QDialog):
    def __init__(
        self,
        password: str = "",
        secondary_password: str = "",
        device_code: str = "",
        phone: str = "",
    ):
        super().__init__()
        self.setWindowTitle("编辑账号")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.edt_password = QLineEdit(password)
        self.edt_secondary = QLineEdit(secondary_password)
        self.edt_device = QLineEdit(device_code)
        self.edt_phone = QLineEdit(phone)
        form.addRow("游戏密码", self.edt_password)
        form.addRow("二级密码", self.edt_secondary)
        form.addRow("设备码", self.edt_device)
        form.addRow("手机号", self.edt_phone)
        layout.addLayout(form)
        btn = QPushButton("保存")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

    def values(self):
        return (
            self.edt_password.text(),
            self.edt_secondary.text(),
            self.edt_device.text().strip(),
            self.edt_phone.text().strip(),
        )


class TrustDialog(QDialog):
    trusted = Signal()

    def __init__(self, session: dict, phone: str, proxy: str | None = None):
        super().__init__()
        self.setWindowTitle("信任设备")
        self._session = session
        self._proxy = proxy
        self._thread = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.edt_phone = QLineEdit(phone)
        self.edt_code = QLineEdit()
        self.edt_code.setPlaceholderText("短信验证码")
        form.addRow("手机号", self.edt_phone)
        form.addRow("验证码", self.edt_code)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.btn_send = QPushButton("发送验证码")
        self.btn_send.clicked.connect(self._send)
        self.btn_trust = QPushButton("确认信任")
        self.btn_trust.clicked.connect(self._trust)
        buttons.addWidget(self.btn_send)
        buttons.addWidget(self.btn_trust)
        layout.addLayout(buttons)
        self.lbl_status = QLabel("")
        layout.addWidget(self.lbl_status)

    def _send(self):
        phone = self.edt_phone.text().strip()
        if not phone:
            QMessageBox.warning(self, "提示", "请填写手机号")
            return
        self.btn_send.setEnabled(False)
        self.lbl_status.setText("正在发送验证码...")
        self._thread = TrustActionThread("send", self._session, phone, proxy=self._proxy)
        self._thread.done.connect(self._on_send_done)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_send_done(self, result):
        self.btn_send.setEnabled(True)
        self.lbl_status.setText("验证码已发送")
        QMessageBox.information(self, "提示", "短信验证码已发送")

    def _trust(self):
        phone = self.edt_phone.text().strip()
        code = self.edt_code.text().strip()
        if not phone or not code:
            QMessageBox.warning(self, "提示", "请填写手机号和验证码")
            return
        self.btn_trust.setEnabled(False)
        self.lbl_status.setText("正在信任设备...")
        self._thread = TrustActionThread(
            "trust", self._session, phone, code, self._proxy
        )
        self._thread.done.connect(self._on_trust_done)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_trust_done(self, result):
        self.trusted.emit()
        self.accept()

    def _on_failed(self, message: str):
        self.btn_send.setEnabled(True)
        self.btn_trust.setEnabled(True)
        self.lbl_status.setText("操作失败")
        QMessageBox.critical(self, "操作失败", message)


class ChangePasswordDialog(QDialog):
    changed = Signal(str)

    def __init__(
        self,
        account: dict,
        new_password: str = "",
        batch_index: int | None = None,
        batch_total: int | None = None,
        proxy: str | None = None,
    ):
        super().__init__()
        title = "修改登录密码"
        if batch_total is not None:
            title = f"批量改密 {batch_index}/{batch_total} - {account['account']}"
        self.setWindowTitle(title)
        self._account = account
        self._proxy = proxy
        self._login_info = None
        self._session = None
        self._thread = None

        layout = QVBoxLayout(self)
        if new_password:
            layout.addWidget(QLabel(f"本次新密码：{new_password}"))
        form = QFormLayout()
        self.lbl_account = QLabel(account["account"])
        self.edt_old = QLineEdit(account["password"])
        self.edt_old.setEchoMode(QLineEdit.Password)
        self.edt_new = QLineEdit()
        self.edt_new.setText(new_password)
        self.edt_new.setEchoMode(QLineEdit.Password)
        self.edt_confirm = QLineEdit()
        self.edt_confirm.setText(new_password)
        self.edt_confirm.setEchoMode(QLineEdit.Password)
        self.edt_phone = QLineEdit(account.get("phone") or "")
        self.edt_code = QLineEdit()
        self.edt_code.setPlaceholderText("短信验证码")
        form.addRow("账号", self.lbl_account)
        form.addRow("旧密码", self.edt_old)
        form.addRow("新密码", self.edt_new)
        form.addRow("确认新密码", self.edt_confirm)
        form.addRow("手机号", self.edt_phone)
        form.addRow("验证码", self.edt_code)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.btn_send = QPushButton("发送验证码")
        self.btn_send.clicked.connect(self._send)
        self.btn_submit = QPushButton("确认修改")
        self.btn_submit.clicked.connect(self._submit)
        buttons.addWidget(self.btn_send)
        buttons.addWidget(self.btn_submit)
        layout.addLayout(buttons)
        self.lbl_status = QLabel("")
        layout.addWidget(self.lbl_status)

    def _send(self):
        old = self.edt_old.text()
        phone = self.edt_phone.text().strip()
        if not old or not phone:
            QMessageBox.warning(self, "提示", "请填写旧密码和手机号")
            return
        self.btn_send.setEnabled(False)
        if query_service.login_type_of(self._account["account"]) == "passport":
            self.lbl_status.setText("正在登录并发送验证码...")
            self._thread = GaiaLoginThread(
                self._account["account"], old, self._proxy
            )
            self._thread.done.connect(self._on_gaia_login)
            self._thread.failed.connect(self._on_failed)
            self._thread.start()
        else:
            self.lbl_status.setText("正在获取会话并发送验证码...")
            self._thread = DashijieSessionThread(
                self._account["account"],
                old,
                self._account.get("device_code") or None,
                self._proxy,
                require_device=False,
            )
            self._thread.done.connect(self._on_dashijie_session)
            self._thread.failed.connect(self._on_failed)
            self._thread.start()

    def _on_gaia_login(self, login_info: dict):
        self._login_info = login_info
        phone = self.edt_phone.text().strip()
        self._thread = SendGaiaPwdCodeThread(login_info, phone, self._proxy)
        self._thread.done.connect(self._on_code_sent)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_dashijie_session(self, session: dict):
        self._session = session
        phone = self.edt_phone.text().strip()
        self._thread = SendWebPwdCodeThread(session, phone, self._proxy)
        self._thread.done.connect(self._on_code_sent)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_code_sent(self, result):
        self.btn_send.setEnabled(True)
        self.lbl_status.setText("验证码已发送")
        QMessageBox.information(self, "提示", "短信验证码已发送")

    def _submit(self):
        old = self.edt_old.text()
        new = self.edt_new.text()
        confirm = self.edt_confirm.text()
        code = self.edt_code.text().strip()
        if not old or not new or not confirm or not code:
            QMessageBox.warning(self, "提示", "请完整填写旧密码、新密码、确认密码和验证码")
            return
        if new != confirm:
            QMessageBox.warning(self, "提示", "两次输入的新密码不一致")
            return
        self.btn_submit.setEnabled(False)
        self.lbl_status.setText("正在修改密码...")
        if query_service.login_type_of(self._account["account"]) == "passport":
            if self._login_info is None:
                QMessageBox.warning(self, "提示", "请先点击“发送验证码”")
                self.btn_submit.setEnabled(True)
                return
            self._thread = ChangePasswordThread(
                self._login_info, old, new, code, self._proxy
            )
        else:
            if self._session is None:
                QMessageBox.warning(self, "提示", "请先点击“发送验证码”")
                self.btn_submit.setEnabled(True)
                return
            self._thread = WebChangePasswordThread(
                self._session,
                self.edt_phone.text().strip(),
                code,
                new,
                self._proxy,
            )
        self._thread.done.connect(self._on_changed)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_changed(self, new_password: str):
        self.changed.emit(new_password)
        self.accept()

    def _on_failed(self, message: str):
        self.btn_send.setEnabled(True)
        self.btn_submit.setEnabled(True)
        self.lbl_status.setText("操作失败")
        QMessageBox.critical(self, "操作失败", message)


class AccountTable(QTableWidget):
    pasteRequested = Signal()
    copyRequested = Signal()

    def __init__(self, rows: int, columns: int, parent=None):
        super().__init__(rows, columns, parent)

    def keyPressEvent(self, event):
        if (
            event.key() == Qt.Key_C
            and event.modifiers() & Qt.ControlModifier
            and self.state() != QAbstractItemView.EditingState
        ):
            self.copyRequested.emit()
        elif (
            event.key() == Qt.Key_V
            and event.modifiers() & Qt.ControlModifier
            and self.currentIndex().column() == 2
            and self.state() != QAbstractItemView.EditingState
        ):
            self.pasteRequested.emit()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        # 勾选列整列点击命中：左键点在第 2 列（勾选）任意位置都切换该行勾选状态
        if (
            event.button() == Qt.LeftButton
            and self.state() != QAbstractItemView.EditingState
        ):
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and index.column() == 1:
                item = self.item(index.row(), 1)
                if item is not None:
                    self.setCurrentIndex(index)
                    item.setCheckState(
                        Qt.Unchecked
                        if item.checkState() == Qt.Checked
                        else Qt.Checked
                    )
                event.accept()
                return
        super().mousePressEvent(event)


class FluentProxyStyle(QProxyStyle):
    """【美化新增-浅色Fluent】复选框统一蓝色勾选外观，不改变交互逻辑。"""

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_IndicatorCheckBox:
            # 勾选框绘制尺寸稍微加大，便于点击与识别
            rect = option.rect.adjusted(-2, -2, 2, 2)
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            if option.state & QStyle.State_On:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#0078D4"))
                painter.drawRoundedRect(rect, 4, 4)
                painter.setPen(
                    QPen(QColor("white"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                )
                painter.drawLine(
                    rect.left() + 4, rect.center().y(),
                    rect.left() + 7, rect.center().y() + 3,
                )
                painter.drawLine(
                    rect.left() + 7, rect.center().y() + 3,
                    rect.right() - 3, rect.top() + 4,
                )
            else:
                painter.setPen(QPen(QColor("#B0B0B0"), 1))
                painter.setBrush(QColor("white"))
                painter.drawRoundedRect(
                    rect.adjusted(1, 1, -1, -1), 4, 4
                )
            painter.restore()
            return
        super().drawPrimitive(element, option, painter, widget)


class MainWindow(QMainWindow):
    def __init__(self, store: LocalAccountStore, card_key: str, server_url: str | None = None):
        super().__init__()
        self._server_url = server_url or DEFAULT_SERVER_URL
        self.setWindowTitle("捕鱼大世界 - 多账户资源查询")
        self.resize(1280, 680)
        self._store = store
        self._card_key = card_key
        self._thread = None
        self._loading_accounts = False
        self._pending_deal = None
        self._last_checked_row = -1
        self._deal_proxy = None
        self._batch_worker = None
        self._welfare_worker = None
        self._welfare_btn = None
        self._welfare_kind = "vip_daily"
        self._bag_qty: dict[int, int] = {}
        self._warehouse_qty: dict[int, int] = {}
        self._proxy_cfg = load_proxy_config()
        self._proxy_pool = ProxyPool(
            self._proxy_cfg.get("api_url", ""),
            self._proxy_cfg.get("per_ip_cap", 8),
            self._proxy_cfg.get("random", True),
        )

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        # 【美化新增-浅色Fluent】卡片式面板
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # 账号管理面板（右侧卡片）
        self.account_card = QFrame()
        self.account_card.setObjectName("accountPanel")
        left = QVBoxLayout(self.account_card)
        left.setContentsMargins(12, 12, 12, 12)
        left.setSpacing(10)
        left.addWidget(QLabel("账号管理"))
        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        search_row.addWidget(QLabel("搜索账号"))
        self.edt_search_account = QLineEdit()
        self.edt_search_account.setPlaceholderText("输入或粘贴游戏账号")
        self.edt_search_account.returnPressed.connect(self._on_search_account)
        search_row.addWidget(self.edt_search_account, 1)
        self.btn_search_account = QPushButton("开始搜索")
        self.btn_search_account.clicked.connect(self._on_search_account)
        search_row.addWidget(self.btn_search_account)
        left.addLayout(search_row)
        self.table_accounts = AccountTable(0, 10)
        # 【美化新增-浅色Fluent】objectName
        self.table_accounts.setObjectName("accountTable")
        self.table_accounts.setHorizontalHeaderLabels(
            ["序号", "勾选", "游戏账号", "游戏密码", "二级密码", "手机号", "设备码", "游戏昵称", "炮台", "充值"]
        )
        self.table_accounts.verticalHeader().setVisible(False)
        self.table_accounts.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_accounts.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        default_widths = [40, 50, 120, 100, 110, 110, 140, 120, 70, 80]
        for col, width in enumerate(default_widths):
            self.table_accounts.setColumnWidth(col, width)
        self.table_accounts.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table_accounts.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed
        )
        self.table_accounts.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_accounts.customContextMenuRequested.connect(self._on_account_menu)
        self.table_accounts.pasteRequested.connect(self._on_paste_accounts)
        self.table_accounts.copyRequested.connect(self._on_copy_accounts)
        self.table_accounts.itemChanged.connect(self._on_account_item_changed)
        left.addWidget(self.table_accounts)

        manage = QHBoxLayout()
        self.chk_proxy = QCheckBox("启用代理")
        self.chk_proxy.setChecked(bool(self._proxy_cfg.get("enabled", False)))
        self.chk_proxy.toggled.connect(self._save_proxy_config)
        manage.addWidget(self.chk_proxy)
        self.edt_proxy_api = QLineEdit()
        # 【美化新增-浅色Fluent】objectName
        self.edt_proxy_api.setObjectName("apiInput")
        self.edt_proxy_api.setPlaceholderText("代理 API 链接")
        self.edt_proxy_api.setText(self._proxy_cfg.get("api_url", ""))
        self.edt_proxy_api.setMinimumWidth(320)
        self.edt_proxy_api.textChanged.connect(self._save_proxy_config)
        manage.addWidget(self.edt_proxy_api, 1)
        self.btn_test_proxy = QPushButton("测试代理")
        self.btn_test_proxy.clicked.connect(self._on_test_proxy)
        manage.addWidget(self.btn_test_proxy)
        left.addLayout(manage)

        delay_row = QHBoxLayout()
        delay_row.setSpacing(4)
        delay_row.addWidget(QLabel("批量刷新间隔(秒)"))
        delay_min_default = self._proxy_cfg.get("delay_min", 30)
        delay_max_default = self._proxy_cfg.get("delay_max", 90)
        if delay_min_default == 30 and delay_max_default == 90:
            delay_min_default, delay_max_default = 5, 15
        self.spin_delay_min = QSpinBox()
        self.spin_delay_min.setObjectName("plainSpin")
        self.spin_delay_min.setRange(0, 600)
        self.spin_delay_min.setValue(int(delay_min_default))
        self.spin_delay_min.setFixedWidth(64)
        self.spin_delay_max = QSpinBox()
        self.spin_delay_max.setObjectName("plainSpin")
        self.spin_delay_max.setRange(0, 600)
        self.spin_delay_max.setValue(int(delay_max_default))
        self.spin_delay_max.setFixedWidth(64)
        delay_row.addWidget(QLabel("最小"))
        delay_row.addWidget(self.spin_delay_min)
        delay_row.addWidget(QLabel("最大"))
        delay_row.addWidget(self.spin_delay_max)
        self.btn_batch_refresh = QPushButton("批量刷新")
        self.btn_batch_refresh.clicked.connect(self._on_batch_refresh)
        delay_row.addWidget(self.btn_batch_refresh)
        delay_row.addStretch()
        self.spin_delay_min.valueChanged.connect(self._on_delay_min_changed)
        self.spin_delay_max.valueChanged.connect(self._on_delay_max_changed)
        left.addLayout(delay_row)
        self._save_proxy_config()

        welfare_row = QHBoxLayout()
        welfare_row.setSpacing(6)
        self.btn_vip_daily = QPushButton("每日vip福利领取")
        self.btn_vip_daily.clicked.connect(
            lambda: self._on_batch_welfare("vip_daily")
        )
        welfare_row.addWidget(self.btn_vip_daily)
        self.btn_thanksgiving = QPushButton("感恩日领取")
        self.btn_thanksgiving.clicked.connect(
            lambda: self._on_batch_welfare("thanksgiving")
        )
        welfare_row.addWidget(self.btn_thanksgiving)
        welfare_row.addStretch()
        left.addLayout(welfare_row)

        left.addWidget(QLabel("批量改密规则"))
        order = QHBoxLayout()
        self.rb_letters_first = QRadioButton("字母在前")
        self.rb_letters_first.setChecked(True)
        order.addWidget(self.rb_letters_first)
        self.spin_letters = QSpinBox()
        self.spin_letters.setObjectName("plainSpin")
        self.spin_letters.setRange(0, 16)
        self.spin_letters.setValue(2)
        order.addWidget(QLabel("字母位数"))
        order.addWidget(self.spin_letters)
        self.rb_digits_first = QRadioButton("数字在前")
        order.addWidget(self.rb_digits_first)
        self.spin_digits = QSpinBox()
        self.spin_digits.setObjectName("plainSpin")
        self.spin_digits.setRange(0, 16)
        self.spin_digits.setValue(4)
        order.addWidget(QLabel("数字位数"))
        order.addWidget(self.spin_digits)
        order.addStretch()
        left.addLayout(order)

        self.edt_fixed_pwd = QLineEdit()
        self.edt_fixed_pwd.setPlaceholderText("指定密码（可选，6-16位字母数字）")
        left.addWidget(self.edt_fixed_pwd)
        self.btn_batch_pwd = QPushButton("开始批量改密")
        self.btn_batch_pwd.clicked.connect(self._on_batch_change_password)
        left.addWidget(self.btn_batch_pwd)

        # 资源面板（左侧卡片）
        self.resource_card = QFrame()
        self.resource_card.setObjectName("resourcePanel")
        right = QVBoxLayout(self.resource_card)
        right.setContentsMargins(12, 12, 12, 12)
        right.setSpacing(10)
        right.addWidget(QLabel("资源信息（右键道具可存入/取出）"))
        table_switch = QHBoxLayout()
        self.btn_tab_bag = QPushButton("背包道具")
        self.btn_tab_bag.setObjectName("tabButton")
        self.btn_tab_bag.setCheckable(True)
        self.btn_tab_bag.setChecked(True)
        self.btn_tab_warehouse = QPushButton("仓库道具")
        self.btn_tab_warehouse.setObjectName("tabButton")
        self.btn_tab_warehouse.setCheckable(True)
        self.tab_group = QButtonGroup(self)
        self.tab_group.addButton(self.btn_tab_bag)
        self.tab_group.addButton(self.btn_tab_warehouse)
        self.btn_tab_bag.clicked.connect(lambda: self._on_resource_tab(True))
        self.btn_tab_warehouse.clicked.connect(lambda: self._on_resource_tab(False))
        table_switch.addWidget(self.btn_tab_bag)
        table_switch.addWidget(self.btn_tab_warehouse)
        table_switch.addStretch()
        right.addLayout(table_switch)
        self.grid_bag = self._make_item_grid("bag")
        self.grid_warehouse = self._make_item_grid("warehouse")
        self.resource_stack = QStackedWidget()
        self.resource_stack.addWidget(self.grid_bag)
        self.resource_stack.addWidget(self.grid_warehouse)
        right.addWidget(self.resource_stack, 1)
        self.lbl_status = QLabel("就绪")
        # 【美化新增-浅色Fluent】objectName
        self.lbl_status.setObjectName("statusLabel")
        right.addWidget(self.lbl_status)
        self.btn_refresh = QPushButton("手动刷新")
        self.btn_refresh.clicked.connect(self._on_refresh)
        right.addWidget(self.btn_refresh)
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("日志"))
        log_header.addStretch()
        self.btn_check_update = QPushButton("检查更新")
        self.btn_check_update.clicked.connect(lambda: self._check_for_update(True))
        log_header.addWidget(self.btn_check_update)
        self.btn_open_log = QPushButton("打开日志目录")
        self.btn_open_log.clicked.connect(self._open_log_dir)
        log_header.addWidget(self.btn_open_log)
        right.addLayout(log_header)
        self.txt_log = QPlainTextEdit()
        # 【美化新增-浅色Fluent】objectName
        self.txt_log.setObjectName("logArea")
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(120)
        right.addWidget(self.txt_log)
        root.addWidget(self.resource_card, 3)
        root.addWidget(self.account_card, 5)

        self._reload_accounts()
        # 【热更新】启动后自动检查一次
        QTimer.singleShot(1500, lambda: self._check_for_update(False))
        # 【安全防护】后台心跳校验
        self._heartbeat = HeartbeatThread(self._server_url, card_key)
        self._heartbeat.ok.connect(self._on_heartbeat_ok)
        self._heartbeat.rejected.connect(self._on_heartbeat_rejected)
        self._heartbeat.network_error.connect(self._on_heartbeat_network_error)
        self._heartbeat.locked.connect(self._on_heartbeat_locked)
        self._heartbeat.start()

    def _icon_pixmap(self, pid: int, name: str) -> QPixmap:
        icon_dir = Path(__file__).resolve().parent / "assets" / "items"
        path = icon_dir / f"{pid}.png"
        if path.exists():
            pix = QPixmap(str(path))
            if not pix.isNull():
                return pix.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pix = QPixmap(96, 96)
        pix.fill(QColor.fromHsv((pid * 47) % 360, 120, 200))
        painter = QPainter(pix)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Microsoft YaHei", 12))
        painter.drawText(pix.rect(), Qt.AlignCenter, str(pid))
        painter.end()
        return pix.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _make_item_grid(self, kind: str) -> QWidget:
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QGridLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        cells: dict[int, tuple[QLabel, QLabel]] = {}
        for index, (pid, name) in enumerate(bydsj_client.ITEMS):
            cell = QWidget()
            # 【美化新增-浅色Fluent】objectName + hover
            cell.setObjectName("iconCard")
            cell.setAttribute(Qt.WA_Hover, True)
            box = QVBoxLayout(cell)
            box.setContentsMargins(4, 4, 4, 4)
            box.setSpacing(2)
            icon = QLabel()
            # 【美化新增-浅色Fluent】objectName + hover
            icon.setObjectName("iconLabel")
            icon.setAttribute(Qt.WA_Hover, True)
            icon.setFixedSize(64, 64)
            icon.setPixmap(self._icon_pixmap(pid, name))
            icon.setAlignment(Qt.AlignCenter)
            icon.setToolTip(name)
            icon.setContextMenuPolicy(Qt.CustomContextMenu)
            icon.customContextMenuRequested.connect(
                lambda pos, p=pid, k=kind, w=icon: self._on_item_menu(k, p, w, pos)
            )
            qty = QLabel("-")
            qty.setObjectName("qtyLabel")
            qty.setAlignment(Qt.AlignCenter)
            qty.setToolTip(name)
            box.addWidget(icon, 0, Qt.AlignHCenter)
            box.addWidget(qty)
            layout.addWidget(cell, index // 4, index % 4)
            cells[pid] = (icon, qty)
        for col in range(4):
            layout.setColumnStretch(col, 1)
        layout.setRowStretch((len(bydsj_client.ITEMS) + 3) // 4, 1)
        if kind == "bag":
            self._bag_cells = cells
        else:
            self._warehouse_cells = cells
        return container

    def _on_resource_tab(self, bag_active: bool):
        self.resource_stack.setCurrentIndex(0 if bag_active else 1)

    def _reload_accounts(self, keep_checked: set[str] | None = None):
        if keep_checked is None:
            checked_rows = self._checked_rows()
            keep_checked = {
                self._account_at(r)["account"] for r in checked_rows
            }
        seq = []
        for r in range(self.table_accounts.rowCount()):
            row_id = self.table_accounts.item(r, 0).data(Qt.UserRole)
            if row_id is None:
                contents = [
                    self.table_accounts.item(r, c).text()
                    if self.table_accounts.item(r, c)
                    else ""
                    for c in (2, 3, 4, 5, 6, 8)
                ]
                seq.append(("blank", contents))
            else:
                seq.append(("db", row_id))
        blank_rows = []
        for i, entry in enumerate(seq):
            if entry[0] != "blank":
                continue
            prev_id = next(
                (seq[j][1] for j in range(i - 1, -1, -1) if seq[j][0] == "db"),
                None,
            )
            next_id = next(
                (seq[j][1] for j in range(i + 1, len(seq)) if seq[j][0] == "db"),
                None,
            )
            blank_rows.append((prev_id, next_id, entry[1]))
        self._loading_accounts = True
        self.table_accounts.setRowCount(0)
        items = self._store.list_accounts()
        for row, item in enumerate(items):
            self.table_accounts.insertRow(row)
            id_item = QTableWidgetItem(str(row + 1))
            id_item.setData(Qt.UserRole, item["id"])
            id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check_item.setCheckState(
                Qt.Checked if item["account"] in keep_checked else Qt.Unchecked
            )
            if item["account"] in keep_checked:
                self._last_checked_row = row
            nickname_item = QTableWidgetItem(item.get("nickname") or "")
            nickname_item.setFlags(nickname_item.flags() & ~Qt.ItemIsEditable)
            cannon_item = QTableWidgetItem(str(item.get("cannon") or 0))
            total_item = QTableWidgetItem(str(item.get("total_infull_num") or 0))
            total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)
            self.table_accounts.setItem(row, 0, id_item)
            self.table_accounts.setItem(row, 1, check_item)
            self.table_accounts.setItem(row, 2, QTableWidgetItem(item["account"]))
            self.table_accounts.setItem(row, 3, QTableWidgetItem(item["password"]))
            self.table_accounts.setItem(row, 4, QTableWidgetItem(item["secondary_password"]))
            self.table_accounts.setItem(row, 5, QTableWidgetItem(item.get("phone") or ""))
            self.table_accounts.setItem(row, 6, QTableWidgetItem(item.get("device_code") or ""))
            self.table_accounts.setItem(row, 7, nickname_item)
            self.table_accounts.setItem(row, 8, cannon_item)
            self.table_accounts.setItem(row, 9, total_item)
        index_of = {item["id"]: index for index, item in enumerate(items)}
        inserted_blanks = 0
        for prev_id, next_id, contents in blank_rows:
            if next_id in index_of:
                insert_at = index_of[next_id] + inserted_blanks
            elif prev_id in index_of:
                insert_at = index_of[prev_id] + 1 + inserted_blanks
            else:
                insert_at = len(items) + inserted_blanks
            self._insert_blank_row(insert_at)
            for col, text in zip((2, 3, 4, 5, 6, 8), contents):
                self.table_accounts.item(insert_at, col).setText(text)
            if self._last_checked_row >= insert_at:
                self._last_checked_row += 1
            inserted_blanks += 1
        self._renumber_rows()
        self._loading_accounts = False

    def _checked_row(self):
        if self._last_checked_row >= 0:
            item = self.table_accounts.item(self._last_checked_row, 1)
            if item is not None and item.checkState() == Qt.Checked:
                return self._last_checked_row
        return self.table_accounts.currentRow()

    def _checked_rows(self):
        rows = []
        for row in range(self.table_accounts.rowCount()):
            item = self.table_accounts.item(row, 1)
            if item is not None and item.checkState() == Qt.Checked:
                rows.append(row)
        return rows

    def _account_at(self, row: int):
        if row < 0 or row >= self.table_accounts.rowCount():
            return None
        return {
            "id": self.table_accounts.item(row, 0).data(Qt.UserRole),
            "account": self.table_accounts.item(row, 2).text(),
            "password": self.table_accounts.item(row, 3).text(),
            "secondary_password": self.table_accounts.item(row, 4).text(),
            "phone": self.table_accounts.item(row, 5).text(),
            "device_code": self.table_accounts.item(row, 6).text(),
            "nickname": self.table_accounts.item(row, 7).text(),
            "cannon": self.table_accounts.item(row, 8).text(),
            "total_infull_num": self.table_accounts.item(row, 9).text(),
        }

    def _on_account_item_changed(self, item):
        if self._loading_accounts:
            return
        column = item.column()
        if column == 1:
            row = item.row()
            if item.checkState() == Qt.Checked:
                account = self._account_at(row)
                if not account or not account["account"].strip():
                    QMessageBox.warning(self, "提示", "该行尚未填写游戏账号，请先填写账号")
                    self._loading_accounts = True
                    item.setCheckState(Qt.Unchecked)
                    self._loading_accounts = False
                    return
                if not (account.get("password") or "").strip():
                    QMessageBox.warning(self, "提示", "该账号未设置密码，请先编辑填写密码")
                    self._loading_accounts = True
                    item.setCheckState(Qt.Unchecked)
                    self._loading_accounts = False
                    return
                self._last_checked_row = row
                self.table_accounts.selectRow(row)
                self.lbl_status.setText(f"已选择账号 {account['account']}，点击手动刷新查询")
            elif row == self._last_checked_row:
                checked = self._checked_rows()
                self._last_checked_row = checked[-1] if checked else -1
        elif column in (2, 3, 4, 5, 6, 8):
            self._save_edited_row(item)

    def _save_edited_row(self, item):
        field_map = {2: "游戏账号", 3: "游戏密码", 4: "二级密码", 5: "手机号", 6: "设备码", 8: "炮台"}
        db_key = {2: "account", 3: "password", 4: "secondary_password", 5: "phone", 6: "device_code", 8: "cannon"}
        column = item.column()
        row = item.row()
        row_id = self.table_accounts.item(row, 0).data(Qt.UserRole)
        old = self._store.get_account(row_id) if row_id else None
        old_value = old[db_key[column]] if old else ""
        new_value = item.text()
        if column == 8:
            try:
                int(new_value or 0)
            except ValueError:
                QMessageBox.warning(self, "提示", "炮台必须填写数字")
                self._loading_accounts = True
                item.setText(str(old_value or ""))
                self._loading_accounts = False
                return
        row_data = self._account_at(row)
        account = row_data["account"].strip()
        if not account:
            if old:
                QMessageBox.warning(self, "提示", "游戏账号不能为空，已恢复原值")
                self._reload_accounts()
            return
        login_type = query_service.login_type_of(account)
        try:
            if old:
                self._store.update_account(
                    old["id"],
                    row_data["password"],
                    row_data["secondary_password"],
                    row_data["device_code"],
                    row_data["phone"],
                    None,
                    None,
                    account,
                    int(row_data["cannon"] or 0),
                )
                self._append_log(
                    f"修改账号字段：账号={account} 字段={field_map[column]} 旧值={old_value} 新值={new_value}"
                )
            else:
                existing = self._store.list_accounts()
                if any(a["account"] == account for a in existing):
                    QMessageBox.warning(self, "提示", f"账号 {account} 已存在，请直接编辑原有账号")
                    self._loading_accounts = True
                    item.setText("")
                    self._loading_accounts = False
                    return
                db_index = sum(
                    1
                    for r in range(row)
                    if self.table_accounts.item(r, 0).data(Qt.UserRole) is not None
                )
                insert_pos = min(db_index, len(existing))
                new_row = self._store.add_account(
                    account,
                    row_data["password"],
                    row_data["secondary_password"],
                    login_type,
                    None,
                    "",
                    row_data["device_code"],
                    row_data["phone"],
                    0,
                    int(row_data["cannon"] or 0),
                    sort_order=0,
                )
                ordered = existing[:insert_pos] + [new_row] + existing[insert_pos:]
                self._store.renumber_accounts([a["id"] for a in ordered])
                self.table_accounts.item(row, 0).setData(Qt.UserRole, new_row["id"])
                self._append_log(
                    f"新增账号（表格编辑）：账号={account} 密码={row_data['password']} "
                    f"二级密码={row_data['secondary_password']} 手机号={row_data['phone']} "
                    f"设备码={row_data['device_code']}"
                )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "保存失败", str(exc))
            self._reload_accounts()
            return

    def _insert_blank_row(self, row: int) -> None:
        prev_loading = self._loading_accounts
        self._loading_accounts = True
        try:
            self.table_accounts.insertRow(row)
            id_item = QTableWidgetItem(str(row + 1))
            id_item.setData(Qt.UserRole, None)
            id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check_item.setCheckState(Qt.Unchecked)
            nickname_item = QTableWidgetItem("")
            nickname_item.setFlags(nickname_item.flags() & ~Qt.ItemIsEditable)
            total_item = QTableWidgetItem("0")
            total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)
            self.table_accounts.setItem(row, 0, id_item)
            self.table_accounts.setItem(row, 1, check_item)
            for col in range(2, 7):
                self.table_accounts.setItem(row, col, QTableWidgetItem(""))
            self.table_accounts.setItem(row, 7, nickname_item)
            self.table_accounts.setItem(row, 8, QTableWidgetItem(""))
            self.table_accounts.setItem(row, 9, total_item)
        finally:
            self._loading_accounts = prev_loading

    def _insert_rows(self, anchor_row: int, above: bool) -> None:
        count, ok = QInputDialog.getInt(
            self, "插入行", "请输入要插入的行数：", 1, 1, 100, 1
        )
        if not ok or count <= 0:
            return
        insert_at = anchor_row if above else anchor_row + 1
        for offset in range(count):
            self._insert_blank_row(insert_at + offset)
        if self._last_checked_row >= 0:
            if above and self._last_checked_row >= anchor_row:
                self._last_checked_row += count
            elif not above and self._last_checked_row > anchor_row:
                self._last_checked_row += count
        self._renumber_rows()
        self.table_accounts.setCurrentCell(insert_at, 2)
        position = "上方" if above else "下方"
        self._append_log(f"插入 {count} 行（第 {anchor_row + 1} 行{position}）")

    def _on_account_menu(self, pos):
        row = self.table_accounts.rowAt(pos.y())
        column = self.table_accounts.columnAt(pos.x())
        if row < 0:
            # 【美化/体验新增】空白区域右击：添加行或直接粘贴账号
            menu = QMenu(self)
            action_add = menu.addAction("添加行")
            action_paste_empty = menu.addAction("粘贴账号数据")
            action = menu.exec(self.table_accounts.viewport().mapToGlobal(pos))
            if action == action_add:
                count, ok = QInputDialog.getInt(
                    self, "添加行", "请输入要添加的行数：", 1, 1, 100, 1
                )
                if ok and count > 0:
                    for _ in range(count):
                        self._insert_blank_row(self.table_accounts.rowCount())
                    self._renumber_rows()
                    self._append_log(f"添加 {count} 行（空白区域）")
            elif action == action_paste_empty:
                self._on_paste_accounts(0)
            return
        menu = QMenu(self)
        action_above = menu.addAction("在上方插入行")
        action_below = menu.addAction("在下方插入行")
        action_copy = menu.addAction("复制")
        menu.addSeparator()
        action_delete_row = menu.addAction("删除此行")
        action_login = action_refresh = action_edit = action_clear = action_paste = None
        if column == 2:
            menu.addSeparator()
            action_login = menu.addAction("登录")
            action_refresh = menu.addAction("刷新")
            action_edit = menu.addAction("编辑账号信息")
            action_clear = menu.addAction("删除账号（清空数据）")
            action_paste = menu.addAction("粘贴账号数据")
        action = menu.exec(self.table_accounts.viewport().mapToGlobal(pos))
        if action is None:
            return
        if action == action_above:
            self._insert_rows(row, above=True)
        elif action == action_below:
            self._insert_rows(row, above=False)
        elif action == action_copy:
            self._on_copy_accounts(row, column)
        elif action == action_delete_row:
            self._delete_row(row)
        elif column == 2 and action == action_paste:
            self._on_paste_accounts(row)
        elif column == 2 and action == action_login:
            account = self._account_at(row)
            if account and account["account"].strip():
                self._append_log(f"登录账号：{account['account']}")
                self._start_refresh(account)
            else:
                self._append_log(f"第 {row + 1} 行为空，跳过登录")
        elif column == 2 and action == action_refresh:
            account = self._account_at(row)
            if account and account["account"].strip():
                self._append_log(f"刷新账号：{account['account']}")
                self._start_refresh(account)
            else:
                self._append_log(f"第 {row + 1} 行为空，跳过刷新")
        elif column == 2 and action == action_edit:
            account = self._account_at(row)
            if account and account["account"].strip():
                self._edit_account(account)
            else:
                self._append_log(f"第 {row + 1} 行为空，跳过编辑")
        elif column == 2 and action == action_clear:
            self._clear_account_row(row)

    def _renumber_rows(self):
        prev_loading = self._loading_accounts
        self._loading_accounts = True
        try:
            for r in range(self.table_accounts.rowCount()):
                item = self.table_accounts.item(r, 0)
                if item is not None:
                    item.setText(str(r + 1))
        finally:
            self._loading_accounts = prev_loading

    def _delete_row(self, row: int):
        row_id = self.table_accounts.item(row, 0).data(Qt.UserRole)
        account_text = self.table_accounts.item(row, 2).text()
        if row_id is not None:
            if (
                QMessageBox.question(
                    self, "确认", f"确定删除账号 {account_text} 所在行吗？"
                )
                != QMessageBox.Yes
            ):
                return
            self._store.delete_account(row_id)
            self._append_log(f"删除账号行：{account_text}（第 {row + 1} 行）")
        else:
            if (
                QMessageBox.question(
                    self, "确认", "确定删除该空白行吗？未保存的内容会丢失。"
                )
                != QMessageBox.Yes
            ):
                return
            self._append_log(f"删除空白行（第 {row + 1} 行）")
        self.table_accounts.removeRow(row)
        if self._last_checked_row == row:
            self._last_checked_row = -1
        elif self._last_checked_row > row:
            self._last_checked_row -= 1
        self._renumber_rows()

    def _on_copy_accounts(self, row: int | None = None, column: int | None = None):
        indexes = self.table_accounts.selectedIndexes()
        if not indexes and row is not None and column is not None:
            indexes = [self.table_accounts.model().index(row, column)]
        if not indexes:
            return
        min_row = min(idx.row() for idx in indexes)
        max_row = max(idx.row() for idx in indexes)
        min_col = min(idx.column() for idx in indexes)
        max_col = max(idx.column() for idx in indexes)
        grid: dict[int, dict[int, str]] = {}
        for idx in indexes:
            item = self.table_accounts.itemFromIndex(idx)
            grid.setdefault(idx.row(), {})[idx.column()] = item.text() if item else ""
        rows: list[list[str]] = []
        for r in range(min_row, max_row + 1):
            rows.append([grid.get(r, {}).get(c, "") for c in range(min_col, max_col + 1)])
        QApplication.clipboard().setText(build_tsv(rows))

    def _clear_account_row(self, row: int):
        account = self._account_at(row)
        if not account or not account["account"].strip():
            self._append_log(f"第 {row + 1} 行为空，跳过删除账号")
            return
        if (
            QMessageBox.question(
                self,
                "确认",
                f"确定清空账号 {account['account']} 的数据吗？将保留第 {row + 1} 行。",
            )
            != QMessageBox.Yes
        ):
            return
        row_id = self.table_accounts.item(row, 0).data(Qt.UserRole)
        if row_id is not None:
            self._store.delete_account(row_id)
        self._loading_accounts = True
        try:
            self.table_accounts.item(row, 0).setData(Qt.UserRole, None)
            for col in (2, 3, 4, 5, 6, 8):
                self.table_accounts.item(row, col).setText("")
            self.table_accounts.item(row, 7).setText("")
            self.table_accounts.item(row, 9).setText("0")
        finally:
            self._loading_accounts = False
        self._append_log(f"清空账号数据：{account['account']}（保留第 {row + 1} 行）")

    def _edit_account(self, account: dict):
        dialog = EditAccountDialog(
            account["password"],
            account["secondary_password"],
            account["device_code"],
            account["phone"],
        )
        if dialog.exec() == QDialog.Accepted:
            password, secondary, device_code, phone = dialog.values()
            self._store.update_account(
                account["id"],
                password,
                secondary,
                device_code,
                phone,
                None,
                None,
                account["account"],
            )
            self._append_log(
                f"编辑账号信息：{account['account']} 密码={password} 二级密码={secondary} 手机号={phone} 设备码={device_code}"
            )
            self._reload_accounts()

    def _on_paste_accounts(self, anchor_row: int | None = None):
        text = QApplication.clipboard().text()
        try:
            rows, errors = parse_account_rows(text)
        except ValueError as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        if anchor_row is None:
            anchor_row = self.table_accounts.currentRow()
        if anchor_row < 0:
            QMessageBox.information(self, "提示", "请先在游戏账号列选择一行作为粘贴位置")
            return

        existing = self._store.list_accounts()
        unique, duplicates = filter_duplicate_accounts(
            rows, {account["account"] for account in existing}
        )

        skipped = []
        if errors:
            skipped.extend(errors)
            self._append_log(f"粘贴跳过 {len(errors)} 行（格式错误）：\n" + "\n".join(errors))
        if duplicates:
            skipped.append("已存在账号：" + "、".join(duplicates))
            self._append_log(f"粘贴跳过 {len(duplicates)} 行（账号已存在）：" + "、".join(duplicates))
        if not unique:
            message = "\n".join(skipped) if skipped else "剪贴板中没有可导入的账号"
            QMessageBox.warning(self, "没有可导入的账号", message)
            return
        if skipped:
            QMessageBox.warning(
                self,
                "部分行未导入",
                "\n".join(skipped) + f"\n共跳过 {len(errors) + len(duplicates)} 行，其余 {len(unique)} 行已导入。",
            )

        blank_flags = [
            self.table_accounts.item(r, 0).data(Qt.UserRole) is None
            for r in range(self.table_accounts.rowCount())
        ]
        targets = paste_target_rows(blank_flags, anchor_row, len(unique))
        for data, target in zip(unique, targets):
            if target < len(blank_flags) and blank_flags[target]:
                self._place_pasted_row(target, data)
            else:
                self._insert_blank_row(target)
                self._place_pasted_row(target, data)
        self._reload_accounts()
        self._append_log(
            f"粘贴完成：新增 {len(unique)} 个账号，从第 {targets[0] + 1} 行开始"
        )

    def _place_pasted_row(self, row_index: int, data: dict):
        existing = self._store.list_accounts()
        db_index = sum(
            1
            for r in range(row_index)
            if self.table_accounts.item(r, 0).data(Qt.UserRole) is not None
        )
        insert_pos = min(db_index, len(existing))
        login_type = query_service.login_type_of(data["account"])
        record = self._store.add_account(
            data["account"],
            data["password"],
            data["secondary_password"],
            login_type,
            None,
            "",
            data["device_code"],
            data["phone"],
            0,
            0,
            sort_order=0,
        )
        ordered = existing[:insert_pos] + [record] + existing[insert_pos:]
        self._store.renumber_accounts([account["id"] for account in ordered])
        self._loading_accounts = True
        try:
            self.table_accounts.item(row_index, 0).setData(Qt.UserRole, record["id"])
            self.table_accounts.item(row_index, 0).setText(str(row_index + 1))
            self.table_accounts.item(row_index, 2).setText(data["account"])
            self.table_accounts.item(row_index, 3).setText(data["password"])
            self.table_accounts.item(row_index, 4).setText(data["secondary_password"])
            self.table_accounts.item(row_index, 5).setText(data["phone"])
            self.table_accounts.item(row_index, 6).setText(data["device_code"])
        finally:
            self._loading_accounts = False
        self._append_log(
            f"导入账号：{data['account']} 密码={data['password']} 二级密码={data['secondary_password']} "
            f"手机号={data['phone']} 设备码={data['device_code']}"
        )

    def _on_item_menu(self, kind: str, prop_id: int, icon: QLabel, pos):
        prop_name = bydsj_client.item_name(prop_id)
        menu = QMenu(self)
        if kind == "bag":
            action = menu.addAction("存入仓库")
            direction = 1
        else:
            action = menu.addAction("取出到背包")
            direction = -1
        qty_map = self._bag_qty if kind == "bag" else self._warehouse_qty
        if menu.exec(icon.mapToGlobal(pos)) == action:
            self._start_deal(prop_id, prop_name, direction, qty_map.get(prop_id, 0))

    def _start_deal(self, prop_id: int, prop_name: str, direction: int, max_raw: int):
        account = self._account_at(self._checked_row())
        if not account:
            QMessageBox.information(self, "提示", "请先勾选一个账号")
            return
        if not (account.get("password") or "").strip():
            QMessageBox.warning(self, "提示", "该账号未设置密码，请先编辑填写密码")
            return
        if not account["secondary_password"]:
            QMessageBox.warning(self, "提示", "该账号未设置二级密码，请先编辑账号填写")
            return
        unit = display_unit(prop_id)
        source_display = max_raw // 10000 if prop_id == 10000 else max_raw
        max_display = deal_max_display(prop_id, max_raw)
        if max_display <= 0:
            QMessageBox.information(self, "提示", "当前可用数量为 0 或已达到上限，无法操作")
            return
        dialog = QuantityDialog(
            f"输入数量（{unit}）", max_display, unit, available=source_display
        )
        if dialog.exec() != QDialog.Accepted:
            return
        quantity = dialog.spin.value()
        deal_num = display_to_deal_num(prop_id, quantity) * direction
        action_text = "存入仓库" if direction > 0 else "取出到背包"
        if (
            QMessageBox.question(
                self,
                "确认操作",
                f"账号：{account['account']}\n道具：{prop_name}\n数量：{quantity}{unit}\n方向：{action_text}\n确认执行吗？",
            )
            != QMessageBox.Yes
        ):
            return
        self._pending_deal = (account, prop_id, deal_num, quantity, unit)
        self._deal_proxy = None
        if self.chk_proxy.isChecked():
            if not self.edt_proxy_api.text().strip():
                QMessageBox.warning(self, "提示", "已启用代理，但未填写 API 链接")
                self._pending_deal = None
                return
            self._deal_proxy = self._proxy_pool.next()
            if self._deal_proxy is None:
                QMessageBox.warning(
                    self, "代理获取失败", self._proxy_pool.last_error or "代理池为空"
                )
                self._pending_deal = None
                return
            self._append_log(f"使用代理 {self._proxy_pool.mask(self._deal_proxy)}")
        self._set_busy(True)
        self.lbl_status.setText("正在检查设备信任...")
        self._thread = TrustCheckThread(
            account["account"],
            account["password"],
            account["device_code"] or None,
            self._deal_proxy,
        )
        self._thread.done.connect(self._on_trust_check_done)
        self._thread.failed.connect(self._on_thread_failed)
        self._thread.start()

    def _on_trust_check_done(self, payload):
        session, trusted = payload
        if not trusted:
            phone = self._pending_deal[0].get("phone") or session.get("mobile") or ""
            dialog = TrustDialog(session, phone, self._deal_proxy)
            if dialog.exec() == QDialog.Accepted:
                self._execute_deal(session)
            else:
                self._set_busy(False)
                self.lbl_status.setText("已取消信任设备")
            return
        self._execute_deal(session)

    def _execute_deal(self, session: dict):
        account, prop_id, deal_num, _display_qty, _unit = self._pending_deal
        self.lbl_status.setText("正在执行存取...")
        self._thread = WarehouseDealThread(
            session,
            prop_id,
            deal_num,
            account["secondary_password"],
            self._deal_proxy,
        )
        self._thread.done.connect(self._on_deal_done)
        self._thread.failed.connect(self._on_thread_failed)
        self._thread.start()

    def _on_deal_done(self, result):
        account, prop_id, deal_num, display_qty, unit = self._pending_deal or (None, None, None, None, None)
        if account:
            direction = "存入仓库" if deal_num > 0 else "取出到背包"
            self._append_log(
                f"存取成功：{account['account']} {direction} "
                f"{bydsj_client.item_name(prop_id)} 数量={display_qty}{unit}"
            )
        QMessageBox.information(self, "成功", "存取成功")
        self._pending_deal = None
        self._set_busy(False)
        self._on_refresh()

    def _on_thread_failed(self, message: str):
        if self._pending_deal:
            account, prop_id, deal_num, display_qty, unit = self._pending_deal
            direction = "存入仓库" if deal_num > 0 else "取出到背包"
            self._append_log(
                f"存取失败：{account['account']} {direction} "
                f"{bydsj_client.item_name(prop_id)} 数量={display_qty}{unit}：{message}"
            )
        self._pending_deal = None
        self._set_busy(False)
        self.lbl_status.setText("操作失败")
        QMessageBox.critical(self, "操作失败", message)

    def _start_refresh(self, account: dict):
        if self._thread and self._thread.isRunning():
            return
        if not (account.get("password") or "").strip():
            QMessageBox.warning(self, "提示", "该账号未设置密码，请先编辑填写密码")
            self.lbl_status.setText(f"账号 {account['account']} 未设置密码，无法查询")
            return
        proxy = None
        if self.chk_proxy.isChecked():
            if not self.edt_proxy_api.text().strip():
                QMessageBox.warning(self, "提示", "已启用代理，但未填写 API 链接")
                return
            proxy = self._proxy_pool.next()
            if proxy is None:
                QMessageBox.warning(
                    self, "代理获取失败", self._proxy_pool.last_error or "代理池为空"
                )
                return
            self._append_log(f"使用代理 {self._proxy_pool.mask(proxy)}")
        self._set_busy(True)
        self.lbl_status.setText(f"正在查询 {account['account']} ...")
        self._thread = AccountDataThread(
            account["account"],
            account["password"],
            account["device_code"] or None,
            proxy,
        )
        self._thread.done.connect(self._on_refresh_done)
        self._thread.failed.connect(self._on_thread_failed)
        self._thread.start()

    def _apply_refresh_result(self, result: dict):
        existing = next(
            (a for a in self._store.list_accounts() if a["account"] == result["account"]),
            None,
        )
        if existing:
            new_phone = existing.get("phone") or result.get("mobile")
            new_nickname = result.get("nickname") or ""
            new_total = result.get(
                "total_infull_num", existing.get("total_infull_num") or 0
            )
            new_cannon = result.get("cannon", existing.get("cannon") or 0)
            if (
                new_phone != existing.get("phone")
                or new_nickname != existing.get("nickname")
                or new_total != existing.get("total_infull_num")
                or new_cannon != existing.get("cannon")
            ):
                self._store.update_account(
                    existing["id"],
                    existing["password"],
                    existing["secondary_password"],
                    None,
                    new_phone or None,
                    new_nickname or None,
                    new_total,
                    None,
                    new_cannon,
                )
                self._reload_accounts()
        for pid, _name in bydsj_client.ITEMS:
            bag_raw = result["items"].get(pid, 0)
            if pid == 10000:
                bag_raw = result.get("money", 0)
            elif pid == 20000:
                bag_raw = result.get("diamond", 0)
            repo_raw = result["repo"].get(pid, 0)
            self._bag_qty[pid] = bag_raw
            self._warehouse_qty[pid] = repo_raw
            bag_display = f"{bag_raw // 10000}亿" if pid == 10000 else str(bag_raw)
            repo_display = f"{repo_raw // 10000}亿" if pid == 10000 else str(repo_raw)
            self._bag_cells[pid][1].setText(bag_display)
            self._warehouse_cells[pid][1].setText(repo_display)
        self.lbl_status.setText(
            f"{result['account']}  {result.get('nickname') or ''}  userID: {result['user_id']}  {datetime.now():%H:%M:%S}"
        )

    def _on_refresh_done(self, result: dict):
        self._apply_refresh_result(result)
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        for btn in (
            self.btn_refresh,
            self.btn_batch_pwd,
            self.btn_test_proxy,
            self.btn_batch_refresh,
            self.btn_vip_daily,
            self.btn_thanksgiving,
            self.chk_proxy,
            self.edt_proxy_api,
        ):
            btn.setEnabled(not busy)

    def _save_proxy_config(self):
        config = {
            "enabled": self.chk_proxy.isChecked(),
            "api_url": self.edt_proxy_api.text().strip(),
            "per_ip_cap": self._proxy_cfg.get("per_ip_cap", 8),
            "delay_min": self.spin_delay_min.value(),
            "delay_max": self.spin_delay_max.value(),
            "random": self._proxy_cfg.get("random", True),
        }
        self._proxy_cfg = config
        save_proxy_config(config)
        self._proxy_pool.set_api(
            config["api_url"], config["per_ip_cap"], config["random"]
        )

    def _on_delay_min_changed(self, value: int):
        if value > self.spin_delay_max.value():
            self.spin_delay_max.setValue(value)
        self._save_proxy_config()

    def _on_delay_max_changed(self, value: int):
        if value < self.spin_delay_min.value():
            self.spin_delay_min.setValue(value)
        self._save_proxy_config()

    def _on_test_proxy(self):
        api_url = self.edt_proxy_api.text().strip()
        if not api_url:
            QMessageBox.warning(self, "提示", "请先填写代理 API 链接")
            return
        self.btn_test_proxy.setEnabled(False)
        self.lbl_status.setText("正在测试代理 API...")
        self._thread = ProxyTestThread(api_url)
        self._thread.done.connect(self._on_proxy_test_done)
        self._thread.failed.connect(self._on_proxy_test_failed)
        self._thread.start()

    def _on_proxy_test_done(self, text: str):
        self.btn_test_proxy.setEnabled(True)
        self.lbl_status.setText("代理测试成功")
        QMessageBox.information(self, "代理测试成功", text)

    def _on_proxy_test_failed(self, message: str):
        self.btn_test_proxy.setEnabled(True)
        self.lbl_status.setText("代理测试失败")
        QMessageBox.critical(self, "代理测试失败", message)

    def _on_batch_refresh(self):
        if self._batch_worker and self._batch_worker.isRunning():
            self._batch_worker.stop()
            self.btn_batch_refresh.setText("正在停止...")
            return
        rows = self._checked_rows()
        accounts = [
            self._account_at(row)
            for row in rows
            if self._account_at(row) and self._account_at(row)["account"].strip()
        ]
        if not accounts:
            QMessageBox.information(self, "提示", "请先勾选要批量刷新的账号")
            return
        enabled = bool(
            self.chk_proxy.isChecked() and self.edt_proxy_api.text().strip()
        )
        self._set_busy(True)
        self.btn_batch_refresh.setEnabled(True)
        self.btn_batch_refresh.setText("停止批量刷新")
        self._batch_worker = BatchRefreshWorker(
            accounts,
            self._proxy_pool,
            self.spin_delay_min.value(),
            self.spin_delay_max.value(),
            enabled,
        )
        self._batch_worker.done.connect(self._on_batch_account_done)
        self._batch_worker.failed.connect(self._on_batch_account_failed)
        self._batch_worker.status.connect(self._on_batch_status)
        self._batch_worker.finished_all.connect(self._on_batch_finished)
        self._batch_worker.start()
        self._append_log(f"开始批量刷新，共 {len(accounts)} 个账号")

    def _on_batch_account_done(
        self, account_id: int, account_name: str, result: dict
    ):
        self._apply_refresh_result(result)
        self._uncheck_account_row(account_id)
        self._append_log(f"批量刷新成功：{account_name}")

    def _on_batch_account_failed(
        self, account_name: str, message: str, proxy: str
    ):
        self._append_log(f"批量刷新失败：{account_name}：{message}")
        if proxy:
            self._append_log(f"失败代理：{mask_proxy(proxy)}")

    def _on_batch_status(self, text: str):
        self.lbl_status.setText(text)

    def _on_batch_finished(self):
        self._set_busy(False)
        self.btn_batch_refresh.setText("批量刷新")
        self._append_log("批量刷新结束")

    def _welfare_label(self, kind: str) -> str:
        return "每日VIP福利" if kind == "vip_daily" else "感恩日VIP尊享福利"

    def _welfare_button(self, kind: str):
        return self.btn_vip_daily if kind == "vip_daily" else self.btn_thanksgiving

    def _on_batch_welfare(self, kind: str):
        label = self._welfare_label(kind)
        btn = self._welfare_button(kind)
        if self._welfare_worker and self._welfare_worker.isRunning():
            self._welfare_worker.stop()
            btn.setText("正在停止...")
            return
        rows = self._checked_rows()
        accounts = [
            self._account_at(row)
            for row in rows
            if self._account_at(row) and self._account_at(row)["account"].strip()
        ]
        if not accounts:
            QMessageBox.information(
                self, "提示", f"请先勾选要批量领取{label}的账号"
            )
            return
        enabled = bool(
            self.chk_proxy.isChecked() and self.edt_proxy_api.text().strip()
        )
        self._set_busy(True)
        btn.setEnabled(True)
        btn.setText("停止批量领取")
        self._welfare_kind = kind
        self._welfare_btn = btn
        self._welfare_worker = WelfareWorker(
            accounts,
            self._proxy_pool,
            self.spin_delay_min.value(),
            self.spin_delay_max.value(),
            enabled,
            kind,
        )
        self._welfare_worker.done.connect(self._on_welfare_account_done)
        self._welfare_worker.failed.connect(self._on_welfare_account_failed)
        self._welfare_worker.status.connect(self._on_batch_status)
        self._welfare_worker.finished_all.connect(self._on_welfare_finished)
        self._welfare_worker.start()
        self._append_log(
            f"开始批量领取{label}，共 {len(accounts)} 个账号"
        )

    def _on_welfare_account_done(
        self, account_id: int, account_name: str, kind: str, result: dict
    ):
        self._uncheck_account_row(account_id)
        if kind == "vip_daily":
            summary = result.get("summary") or "无明细"
            self._append_log(
                f"每日VIP福利领取成功：{account_name}：{summary}"
            )
        else:
            claim = result.get("claim") or {}
            summary = welfare.format_thanksgiving_summary(claim)
            self._append_log(
                f"感恩日VIP尊享福利领取成功：{account_name}：{summary}"
            )

    def _on_welfare_account_failed(
        self, account_name: str, message: str, proxy: str
    ):
        label = self._welfare_label(self._welfare_kind)
        self._append_log(f"{label}领取失败：{account_name}：{message}")
        if proxy:
            self._append_log(f"失败代理：{mask_proxy(proxy)}")

    def _on_welfare_finished(self):
        self._set_busy(False)
        btn = self._welfare_btn
        if btn is not None:
            btn.setText(
                "每日vip福利领取"
                if self._welfare_kind == "vip_daily"
                else "感恩日领取"
            )
        self._append_log("批量领取结束")

    def _acquire_proxy(self) -> str | None:
        if not self.chk_proxy.isChecked():
            return None
        if not self.edt_proxy_api.text().strip():
            QMessageBox.warning(self, "提示", "已启用代理，但未填写 API 链接")
            return None
        proxy = self._proxy_pool.next()
        if proxy is None:
            QMessageBox.warning(
                self, "代理获取失败", self._proxy_pool.last_error or "代理池为空"
            )
            return None
        self._append_log(f"使用代理 {self._proxy_pool.mask(proxy)}")
        return proxy

    def _append_log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.txt_log.appendPlainText(line)
        try:
            base = os.environ.get("APPDATA")
            log_path = (
                Path(base) / "BydsjManager" / "logs" / "operation.log"
                if base
                else Path(__file__).resolve().parent / "logs" / "operation.log"
            )
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _open_log_dir(self):
        try:
            base = os.environ.get("APPDATA") or str(Path.home() / ".config")
            log_dir = Path(base) / "BydsjManager" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(log_dir))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "打开失败", f"无法打开日志目录：{exc}")

    def _parse_version(self, version: str) -> tuple:
        return tuple(int(x) for x in str(version).split("."))

    def _check_for_update(self, manual: bool):
        if getattr(self, "_update_checking", False):
            return
        self._update_checking = True
        self.btn_check_update.setEnabled(False)
        self._update_thread = UpdateCheckThread(DEFAULT_SERVER_URL)
        self._update_thread.done.connect(
            lambda info: self._on_update_check_done(info, manual)
        )
        self._update_thread.failed.connect(
            lambda msg: self._on_update_check_failed(msg, manual)
        )
        self._update_thread.start()

    def _on_update_check_done(self, info: dict, manual: bool):
        self._update_checking = False
        self.btn_check_update.setEnabled(True)
        try:
            remote = self._parse_version(info["version"])
        except Exception:
            remote = (0, 0, 0)
        if remote > self._parse_version(APP_VERSION):
            note = info.get("note") or "无"
            if (
                QMessageBox.question(
                    self,
                    "发现新版本",
                    f"发现新版本 {info['version']}\n更新说明：{note}\n\n是否立即更新？",
                )
                == QMessageBox.Yes
            ):
                self._start_update_download(info)
            else:
                self._append_log(f"用户跳过更新 {info['version']}")
        else:
            if manual:
                QMessageBox.information(self, "检查更新", "当前已是最新版本")
            self._append_log("检查更新：已是最新版本")

    def _on_update_check_failed(self, message: str, manual: bool):
        self._update_checking = False
        self.btn_check_update.setEnabled(True)
        if manual:
            QMessageBox.warning(self, "检查更新失败", message)
        self._append_log(f"检查更新失败：{message}")

    def _start_update_download(self, info: dict):
        version = info["version"]
        base = os.environ.get("APPDATA") or str(Path.home() / ".config")
        target = (
            Path(base)
            / "BydsjManager"
            / "updates"
            / f"app_{version}.exe"
        )
        url = DEFAULT_SERVER_URL.rstrip("/") + info["url"]
        self._progress = QProgressDialog(
            "正在下载新版本...", "取消", 0, 100, self
        )
        self._progress.setWindowTitle("更新")
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._download_thread = UpdateDownloadThread(url, str(target))
        self._download_thread.progress.connect(self._progress.setValue)
        self._download_thread.done.connect(
            lambda path: self._on_download_done(path, info)
        )
        self._download_thread.failed.connect(self._on_download_failed)
        self._progress.canceled.connect(self._download_thread.requestInterruption)
        self._download_thread.start()

    def _on_download_done(self, path: str, info: dict):
        self._progress.close()
        expected = (info.get("sha256") or "").lower()
        actual = hashlib.sha256(Path(path).read_bytes()).hexdigest().lower()
        if expected and actual != expected:
            QMessageBox.critical(self, "更新失败", "文件校验失败，已保留旧版本")
            self._append_log("更新下载校验失败")
            return
        if not getattr(sys, "frozen", False):
            QMessageBox.information(
                self, "更新", f"开发模式已下载新版本到：\n{path}"
            )
            return
        self._launch_updater(str(Path(sys.executable).resolve()), path)
        self._append_log(f"开始应用更新 {info['version']}")

    def _on_download_failed(self, message: str):
        self._progress.close()
        QMessageBox.critical(self, "更新失败", message)
        self._append_log(f"更新下载失败：{message}")

    def _launch_updater(self, target: str, new_path: str):
        base = os.environ.get("APPDATA") or str(Path.home() / ".config")
        updates_dir = Path(base) / "BydsjManager" / "updates"
        updater_src = None
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", None)
            candidates = []
            if meipass:
                candidates.append(Path(meipass) / "updater" / "updater.exe")
            candidates.append(Path(sys.executable).resolve().parent / "updater" / "updater.exe")
            candidates.append(Path(sys.executable).resolve().parent / "updater.exe")
            for candidate in candidates:
                if candidate.exists():
                    updater_src = candidate
                    break
        else:
            candidate = (
                Path(__file__).resolve().parent.parent / "dist" / "updater.exe"
            )
            if candidate.exists():
                updater_src = candidate
        if updater_src is None:
            QMessageBox.critical(self, "更新失败", "未找到更新程序 updater.exe")
            return
        updater_dst = updates_dir / "updater.exe"
        updates_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(updater_src), str(updater_dst))
        subprocess.Popen(
            [str(updater_dst), "--target", target, "--new", new_path]
        )
        QTimer.singleShot(800, QApplication.instance().quit)

    def _apply_password_change(self, account: dict, new_password: str):
        self._store.update_account(
            account["id"],
            new_password,
            account["secondary_password"],
            account["device_code"],
            account["phone"],
        )
        self._reload_accounts()
        self._uncheck_account_row(account["id"])
        self.lbl_status.setText(f"账号 {account['account']} 密码已修改并更新")
        self._append_log(f"修改密码成功：{account['account']} -> {new_password}")

    def _uncheck_account_row(self, account_id: int):
        for row in range(self.table_accounts.rowCount()):
            id_item = self.table_accounts.item(row, 0)
            if id_item is None or id_item.data(Qt.UserRole) != account_id:
                continue
            check_item = self.table_accounts.item(row, 1)
            if check_item is not None and check_item.checkState() == Qt.Checked:
                self._loading_accounts = True
                check_item.setCheckState(Qt.Unchecked)
                self._loading_accounts = False
            if self._last_checked_row == row:
                remaining = self._checked_rows()
                self._last_checked_row = remaining[-1] if remaining else -1
            break

    def _on_batch_change_password(self):
        rows = self._checked_rows()
        if not rows:
            QMessageBox.information(self, "提示", "请先勾选要批量改密的账号")
            return
        fixed = self.edt_fixed_pwd.text().strip()
        passwords = []
        if fixed:
            if not validate_password(fixed):
                QMessageBox.warning(self, "提示", "指定密码必须是 6-16 位字母数字")
                return
            passwords = [fixed] * len(rows)
        else:
            letters = self.spin_letters.value()
            digits = self.spin_digits.value()
            letters_first = self.rb_letters_first.isChecked()
            try:
                passwords = [
                    generate_password(letters, digits, letters_first) for _ in rows
                ]
            except ValueError as exc:
                QMessageBox.warning(self, "提示", str(exc))
                return
        accounts = [self._account_at(row) for row in rows]
        self._append_log(f"开始批量改密，共 {len(accounts)} 个账号")
        for index, (account, new_pwd) in enumerate(zip(accounts, passwords), 1):
            if not account:
                continue
            self._append_log(f"正在处理 {index}/{len(accounts)}：{account['account']}")
            proxy = self._acquire_proxy()
            if self.chk_proxy.isChecked() and proxy is None:
                self._append_log(f"账号 {account['account']} 代理获取失败，跳过")
                continue
            dialog = ChangePasswordDialog(
                account,
                new_password=new_pwd,
                batch_index=index,
                batch_total=len(accounts),
                proxy=proxy,
            )
            if dialog.exec() == QDialog.Accepted:
                self._apply_password_change(account, new_pwd)
            else:
                if (
                    QMessageBox.question(self, "提示", f"账号 {account['account']} 未完成，是否继续下一个？")
                    != QMessageBox.Yes
                ):
                    self._append_log("批量改密已中止")
                    break
        self._append_log("批量改密流程结束")

    def _on_refresh(self):
        account = self._account_at(self._checked_row())
        if account:
            self._start_refresh(account)
        else:
            QMessageBox.information(self, "提示", "请先勾选一个账号")

    def _on_search_account(self):
        query = self.edt_search_account.text()
        names = []
        for row in range(self.table_accounts.rowCount()):
            item = self.table_accounts.item(row, 2)
            names.append(item.text() if item is not None else "")
        matched = find_account_rows(names, query)
        for line in format_search_log(query, matched):
            self._append_log(line)
        if matched:
            first = matched[0]
            self.table_accounts.selectRow(first)
            target_item = self.table_accounts.item(first, 2)
            if target_item is not None:
                self.table_accounts.scrollToItem(target_item)

    def _on_heartbeat_ok(self):
        self._append_log("检验通过")

    def _on_heartbeat_network_error(self, message: str):
        self._append_log(f"网络异常，宽限期内自动重试：{message}")

    def _on_heartbeat_rejected(self, message: str):
        self._append_log(f"校验失败，软件即将退出：{message}")
        QMessageBox.critical(self, "卡密已失效", f"{message}\n请联系管理员。")
        self.close()

    def _on_heartbeat_locked(self, message: str):
        self._append_log(f"长时间无法连接服务器，软件已锁定：{message}")
        QMessageBox.critical(self, "卡密已失效", "服务器长时间无法校验卡密，软件已锁定。\n请联系管理员。")
        self.close()

    def closeEvent(self, event):
        self._append_log(f"[会话结束] {datetime.now():%Y-%m-%d %H:%M:%S}")
        self._heartbeat.stop()
        self._heartbeat.wait(3000)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    # 【热更新/打包】设置程序窗口图标（任务栏/标题栏）
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        icon_path = (
            Path(meipass) / "assets" / "app_icon.ico"
            if meipass
            else Path(sys.executable).resolve().parent / "assets" / "app_icon.ico"
        )
    else:
        icon_path = Path(__file__).resolve().parent / "assets" / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    # 【美化新增-浅色Fluent】全局复选框蓝色勾选
    app.setStyle(FluentProxyStyle(app.style()))
    # 【美化新增-浅色Fluent】应用全局主题
    app.setStyleSheet(THEME_QSS)
    dialog = ActivationDialog()
    if dialog.exec() != QDialog.Accepted:
        return
    win = MainWindow(dialog.store, dialog.card_key, dialog.server_url)
    if icon_path.exists():
        win.setWindowIcon(QIcon(str(icon_path)))
    win._append_log("════════════════════════════════════════")
    win._append_log(f"[会话开始] {datetime.now():%Y-%m-%d %H:%M:%S} 版本 {APP_VERSION}")
    win._append_log(f"卡密：{mask_card_key(dialog.card_key)}")
    win._append_log("════════════════════════════════════════")
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
