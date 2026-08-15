"""卡密管理端：生成、导出、停用、解绑卡密。"""

import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# 【部署配置】服务器地址内置，登录界面不展示；更换服务器时修改此处后重新打包/热更新
DEFAULT_SERVER_URL = "http://47.100.188.139:18432"


def format_beijing(value) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


class AdminClient:
    def __init__(self, server_url: str, token: str = ""):
        self._server_url = server_url.rstrip("/")
        self._token = token
        self._http = httpx.Client(timeout=15, trust_env=False)

    def _headers(self):
        return {"Authorization": f"Bearer {self._token}"}

    def _raise(self, resp):
        try:
            detail = resp.json().get("detail", resp.text[:200])
        except Exception:
            detail = resp.text[:200]
        raise RuntimeError(detail)

    def login(self, username: str, password: str) -> str:
        resp = self._http.post(self._server_url + "/api/admin/login", json={"username": username, "password": password})
        if resp.status_code != 200:
            self._raise(resp)
        self._token = resp.json()["token"]
        return self._token

    def list_keys(self) -> list[dict]:
        resp = self._http.get(self._server_url + "/api/admin/keys", headers=self._headers())
        if resp.status_code != 200:
            self._raise(resp)
        return resp.json()["items"]

    def generate(self, count: int, card_type: str | None, remark: str | None) -> list[dict]:
        resp = self._http.post(
            self._server_url + "/api/admin/keys/generate",
            json={"count": count, "card_type": card_type, "remark": remark},
            headers=self._headers(),
        )
        if resp.status_code != 200:
            self._raise(resp)
        return resp.json()["keys"]

    def set_status(self, key_id: int, status: str):
        resp = self._http.patch(
            self._server_url + f"/api/admin/keys/{key_id}/status",
            json={"status": status},
            headers=self._headers(),
        )
        if resp.status_code != 200:
            self._raise(resp)

    def unbind(self, key_id: int):
        resp = self._http.post(self._server_url + f"/api/admin/keys/{key_id}/unbind", headers=self._headers())
        if resp.status_code != 200:
            self._raise(resp)

    def renew(self, key_id: int, card_type: str) -> dict:
        resp = self._http.post(
            self._server_url + f"/api/admin/keys/{key_id}/renew",
            json={"card_type": card_type},
            headers=self._headers(),
        )
        if resp.status_code != 200:
            self._raise(resp)
        return resp.json()

    def delete_key(self, key_id: int) -> dict:
        resp = self._http.delete(
            self._server_url + f"/api/admin/keys/{key_id}",
            headers=self._headers(),
        )
        if resp.status_code != 200:
            self._raise(resp)
        return resp.json()

    def add_release(self, version: str, note: str, file_path: str) -> dict:
        with open(file_path, "rb") as f:
            resp = self._http.post(
                self._server_url + "/api/admin/release",
                data={"version": version, "note": note},
                files={"file": (Path(file_path).name, f, "application/octet-stream")},
                headers=self._headers(),
                timeout=600,
            )
        if resp.status_code != 200:
            self._raise(resp)
        return resp.json()


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("管理端登录")
        self.client = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.edt_user = QLineEdit("admin")
        self.edt_password = QLineEdit()
        self.edt_password.setEchoMode(QLineEdit.Password)
        form.addRow("管理员账号", self.edt_user)
        form.addRow("管理员密码", self.edt_password)
        layout.addLayout(form)
        btn = QPushButton("登录")
        btn.clicked.connect(self._login)
        layout.addWidget(btn)
        self.lbl_status = QLabel("")
        layout.addWidget(self.lbl_status)

    def _login(self):
        try:
            client = AdminClient(DEFAULT_SERVER_URL)
            client.login(self.edt_user.text().strip(), self.edt_password.text())
            self.client = client
            self.accept()
        except Exception as exc:  # noqa: BLE001
            self.lbl_status.setText("登录失败")
            QMessageBox.critical(self, "登录失败", str(exc))


class GenerateDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("批量生成卡密")
        self.result = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 200)
        self.spin_count.setValue(10)
        self.combo_type = QComboBox()
        self.combo_type.addItems(
            ["小时卡", "一天卡", "一周卡", "一月卡", "季度卡", "半年卡", "一年卡", "两年卡", "三年卡", "终身卡"]
        )
        self.edt_remark = QLineEdit()
        self.edt_remark.setPlaceholderText("备注，例如：发给张三")
        form.addRow("数量", self.spin_count)
        form.addRow("卡型", self.combo_type)
        form.addRow("备注", self.edt_remark)
        layout.addLayout(form)
        btn = QPushButton("生成")
        btn.clicked.connect(self._generate)
        layout.addWidget(btn)

    def _generate(self):
        card_type = self.combo_type.currentText()
        remark = self.edt_remark.text().strip() or None
        self.result = (self.spin_count.value(), card_type, remark)
        self.accept()


class ReleaseDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("发布用户端新版本")
        self.result = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.edt_version = QLineEdit("1.0.1")
        self.edt_note = QTextEdit()
        self.edt_note.setFixedHeight(80)
        self.edt_file = QLineEdit()
        self.edt_file.setReadOnly(True)
        self.edt_file.setPlaceholderText("请选择用户端 exe")
        btn_file = QPushButton("选择文件")
        btn_file.clicked.connect(self._pick_file)
        file_row = QHBoxLayout()
        file_row.addWidget(self.edt_file, 1)
        file_row.addWidget(btn_file)
        form.addRow("版本号", self.edt_version)
        form.addRow("更新说明", self.edt_note)
        form.addRow("安装包", file_row)
        layout.addLayout(form)
        btn_upload = QPushButton("上传发布")
        btn_upload.clicked.connect(self._upload)
        layout.addWidget(btn_upload)
        self.lbl_status = QLabel("")
        layout.addWidget(self.lbl_status)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择用户端 exe", "", "EXE (*.exe)")
        if path:
            self.edt_file.setText(path)

    def _upload(self):
        version = self.edt_version.text().strip()
        file_path = self.edt_file.text().strip()
        if not version or not file_path:
            QMessageBox.warning(self, "提示", "请填写版本号并选择 exe 文件")
            return
        self.result = {
            "version": version,
            "note": self.edt_note.toPlainText().strip(),
            "file_path": file_path,
        }
        self.accept()


class RenewDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("续费时间")
        self.result = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.combo_type = QComboBox()
        self.combo_type.addItems(
            ["小时卡", "一天卡", "一周卡", "一月卡", "季度卡", "半年卡", "一年卡", "两年卡", "三年卡", "终身卡"]
        )
        form.addRow("续费卡型", self.combo_type)
        layout.addLayout(form)
        btn = QPushButton("确认续费")
        btn.clicked.connect(self._confirm)
        layout.addWidget(btn)

    def _confirm(self):
        self.result = self.combo_type.currentText()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, client: AdminClient):
        super().__init__()
        self.setWindowTitle("卡密管理端")
        self.resize(900, 500)
        self._client = client
        self._last_generated: list[dict] = []

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["ID", "卡密", "状态", "到期时间", "绑定机器", "绑定时间", "备注", "创建时间"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.btn_generate = QPushButton("生成卡密")
        self.btn_refresh = QPushButton("刷新")
        self.btn_export = QPushButton("导出卡密 CSV")
        self.btn_disable = QPushButton("停用")
        self.btn_enable = QPushButton("启用")
        self.btn_unbind = QPushButton("解绑")
        self.btn_renew = QPushButton("续费时间")
        self.btn_delete_card = QPushButton("删除卡密")
        self.btn_release = QPushButton("发布版本")
        self.btn_generate.clicked.connect(self._generate)
        self.btn_refresh.clicked.connect(self._refresh)
        self.btn_export.clicked.connect(self._export_generated)
        self.btn_disable.clicked.connect(lambda: self._set_status("disabled"))
        self.btn_enable.clicked.connect(lambda: self._set_status("active"))
        self.btn_unbind.clicked.connect(self._unbind)
        self.btn_renew.clicked.connect(self._renew)
        self.btn_delete_card.clicked.connect(self._delete_card)
        self.btn_release.clicked.connect(self._publish_release)
        for btn in (self.btn_generate, self.btn_refresh, self.btn_export, self.btn_disable, self.btn_enable, self.btn_unbind, self.btn_renew, self.btn_delete_card, self.btn_release):
            buttons.addWidget(btn)
        layout.addLayout(buttons)
        self._refresh()

    def _publish_release(self):
        dialog = ReleaseDialog()
        if dialog.exec() != QDialog.Accepted or not dialog.result:
            return
        info = dialog.result
        try:
            result = self._client.add_release(
                info["version"], info["note"], info["file_path"]
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "发布失败", str(exc))
            return
        QMessageBox.information(
            self,
            "发布成功",
            f"已发布版本 {result['version']}\nSHA-256: {result['sha256'][:16]}...",
        )

    def _refresh(self):
        try:
            items = self._client.list_keys()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "刷新失败", str(exc))
            return
        self.table.setRowCount(0)
        for row, item in enumerate(items):
            self.table.insertRow(row)
            for col, key in enumerate(["id", "key", "status", "expires_at", "machine_id", "bound_at", "remark", "created_at"]):
                value = item.get(key)
                if col in (3, 5, 7):
                    value = format_beijing(value)
                self.table.setItem(row, col, QTableWidgetItem(str(value or "")))

    def _selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return int(self.table.item(row, 0).text())

    def _generate(self):
        dialog = GenerateDialog()
        if dialog.exec() != QDialog.Accepted:
            return
        count, card_type, remark = dialog.result
        try:
            keys = self._client.generate(count, card_type, remark)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "生成失败", str(exc))
            return
        self._last_generated = keys
        text = "\n".join(k["key"] for k in keys)
        view = QTextEdit()
        view.setPlainText(text)
        view.setReadOnly(True)
        view.setMinimumSize(500, 300)
        view.show()
        QMessageBox.information(self, "生成成功", f"已生成 {len(keys)} 张卡密，请复制或导出。")
        self._refresh()

    def _renew(self):
        key_id = self._selected_id()
        if key_id is None:
            QMessageBox.information(self, "提示", "请先选择要续费的卡密")
            return
        dialog = RenewDialog()
        if dialog.exec() != QDialog.Accepted or not dialog.result:
            return
        try:
            result = self._client.renew(key_id, dialog.result)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "续费失败", str(exc))
            return
        QMessageBox.information(
            self,
            "续费成功",
            f"新到期时间：{format_beijing(result.get('expires_at'))}",
        )
        self._refresh()

    def _delete_card(self):
        key_id = self._selected_id()
        if key_id is None:
            QMessageBox.information(self, "提示", "请先选择要删除的卡密")
            return
        if (
            QMessageBox.question(self, "确认", "确定永久删除这张卡密吗？删除后无法恢复。")
            != QMessageBox.Yes
        ):
            return
        try:
            self._client.delete_key(key_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "删除失败", str(exc))
            return
        QMessageBox.information(self, "删除成功", "卡密已删除")
        self._refresh()

    def _export_generated(self):
        if not self._last_generated:
            QMessageBox.information(self, "提示", "请先批量生成卡密，再导出本次生成的卡密")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存卡密", "card_keys.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["卡密", "ID"])
            for item in self._last_generated:
                writer.writerow([item["key"], item["id"]])
        QMessageBox.information(self, "完成", f"已导出到 {path}")

    def _set_status(self, status: str):
        key_id = self._selected_id()
        if key_id is None:
            QMessageBox.information(self, "提示", "请先选择卡密")
            return
        try:
            self._client.set_status(key_id, status)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "操作失败", str(exc))
            return
        self._refresh()

    def _unbind(self):
        key_id = self._selected_id()
        if key_id is None:
            QMessageBox.information(self, "提示", "请先选择卡密")
            return
        if QMessageBox.question(self, "确认", "确定解绑这台机器吗？") != QMessageBox.Yes:
            return
        try:
            self._client.unbind(key_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "解绑失败", str(exc))
            return
        self._refresh()


def main():
    app = QApplication(sys.argv)
    dialog = LoginDialog()
    if dialog.exec() != QDialog.Accepted:
        return
    win = MainWindow(dialog.client)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
