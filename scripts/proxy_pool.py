"""动态代理池：从抖大代理 API 拉取短效代理，按过期时间与承载上限轮换。"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# 代理 API 缺省时效（分钟）：链接没带 lifetime 时按此兜底
DEFAULT_LIFETIME_MINUTES = 5


def proxy_config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "BydsjManager" / "proxy_config.json"


def _lifetime_minutes(api_url: str) -> int:
    try:
        query = urllib.parse.urlsplit(api_url).query
        value = urllib.parse.parse_qs(query).get(
            "lifetime", [str(DEFAULT_LIFETIME_MINUTES)]
        )[0]
        return max(1, int(value))
    except Exception:
        return DEFAULT_LIFETIME_MINUTES


def normalize_api_url(
    api_url: str, default_lifetime: int = DEFAULT_LIFETIME_MINUTES
) -> str:
    """自动补齐代理 API 参数（用户无需手动改链接）：
    - format=json：统一结构化返回；
    - detail=1：返回真实 deadline（过期时间），轮换精确；
    - lifetime：缺失时按默认时效兜底。
    已存在的参数保持不变，不重复添加。
    """
    parsed = urllib.parse.urlsplit(api_url)
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    keys = {key for key, _ in pairs}
    if "format" not in keys:
        pairs.append(("format", "json"))
    if "detail" not in keys:
        pairs.append(("detail", "1"))
    if "lifetime" not in keys:
        pairs.append(("lifetime", str(max(1, int(default_lifetime)))))
    query = urllib.parse.urlencode(pairs)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
    )


def _parse_deadline(value: str | None, api_url: str) -> float:
    now = time.time()
    if not value:
        return now + _lifetime_minutes(api_url) * 60
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue
    try:
        return float(text)
    except ValueError:
        return now + _lifetime_minutes(api_url) * 60


def _build_proxy_url(ip: str, port, user: str, pwd: str) -> str:
    if user or pwd:
        return (
            "http://"
            + urllib.parse.quote(user, safe="")
            + ":"
            + urllib.parse.quote(pwd, safe="")
            + "@"
            + ip
            + ":"
            + str(port)
        )
    return f"http://{ip}:{port}"


def _parse_text_entries(text: str, api_url: str) -> list[dict]:
    """解析 txt/cstm 格式返回：每行一个代理，字段按 Tab/空格/冒号拆分。"""
    entries: list[dict] = []

    def is_ipv4(value: str) -> bool:
        parts = value.split(".")
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(p) <= 255 for p in parts)
        except ValueError:
            return False

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = None
        for splitter in ("\t", None, ":"):
            if splitter is None:
                candidate = line.split()
            else:
                candidate = line.split(splitter)
            candidate = [p.strip() for p in candidate if p.strip()]
            if len(candidate) in (2, 4, 5):
                parts = candidate
                break
        if parts is None:
            continue
        ip = parts[0]
        if not is_ipv4(ip) or not parts[1].isdigit():
            continue
        port = parts[1]
        user = parts[2] if len(parts) >= 4 else ""
        pwd = parts[3] if len(parts) >= 4 else ""
        deadline = parts[4] if len(parts) >= 5 else None
        entries.append(
            {
                "proxy": _build_proxy_url(ip, port, user, pwd),
                "deadline_ts": _parse_deadline(deadline, api_url),
                "used": 0,
                "host": f"{ip}:{port}",
            }
        )
    if not entries:
        raise RuntimeError("代理 API 返回为空或字段无法识别")
    return entries


def fetch_proxies(api_url: str, timeout: float = 15.0) -> list[dict]:
    """调用代理 API，返回代理条目列表（含 proxy/deadline_ts）。"""
    api_url = normalize_api_url(api_url)
    req = urllib.request.Request(api_url, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        return _parse_text_entries(raw.decode("utf-8", errors="replace"), api_url)

    if isinstance(data, dict):
        ret = data.get("ret")
        if ret not in (200, None):
            raise RuntimeError(
                f"代理 API 返回错误 ret={ret} msg={data.get('msg') or ''}"
            )
        wrapped = data.get("data") or data.get("list") or data.get("proxies")
        candidates = wrapped if isinstance(wrapped, list) else [data]
    elif isinstance(data, list):
        candidates = data
    else:
        raise RuntimeError("代理 API 返回格式无法识别")

    outer_deadline = data.get("deadline") if isinstance(data, dict) else None
    entries: list[dict] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        ip = str(item.get("ip") or "").strip()
        port = item.get("port")
        if not ip or port is None:
            continue
        user = str(item.get("user") or "")
        pwd = str(item.get("pwd") or "")
        deadline = item.get("deadline") or outer_deadline
        entries.append(
            {
                "proxy": _build_proxy_url(ip, port, user, pwd),
                "deadline_ts": _parse_deadline(deadline, api_url),
                "used": 0,
                "host": f"{ip}:{port}",
            }
        )
    if not entries:
        raise RuntimeError("代理 API 返回为空或字段缺失")
    return entries


def mask_proxy(proxy: str) -> str:
    """去掉代理里的账号密码，只显示 host:port。"""
    try:
        parsed = urllib.parse.urlsplit(proxy)
        host = parsed.hostname or ""
        port = parsed.port
        return f"{host}:{port}" if port else host
    except Exception:
        return proxy


class ProxyPool:
    def __init__(
        self,
        api_url: str = "",
        per_ip_cap: int = 8,
        random_order: bool = True,
    ):
        self._api_url = api_url
        self._cap = max(1, per_ip_cap)
        self._random = random_order
        self._entries: list[dict] = []
        self._index = 0
        self._bindings: dict[str, str] = {}
        self.fetch_count = 0
        self.last_error: str | None = None

    def set_api(
        self, api_url: str, per_ip_cap: int = 8, random_order: bool = True
    ) -> None:
        self._api_url = api_url.strip()
        self._cap = max(1, per_ip_cap)
        self._random = random_order
        self._entries = []
        self._index = 0
        self._bindings = {}
        self.fetch_count = 0
        self.last_error = None

    def _refill(self) -> None:
        self.last_error = None
        entries = fetch_proxies(self._api_url)
        self._entries = entries
        self._index = 0
        self.fetch_count += 1

    def next(self, account: str | None = None) -> str | None:
        """取一个可用代理；传入账号时优先复用该账号绑定的 IP（账号-IP 亲和）。

        绑定的 IP 有效期内同一账号始终走同一出口 IP，避免游戏会话因 IP 变化失效；
        IP 过期/超载/失败后自动换新 IP 并重新绑定。
        """
        now = time.time()
        self._entries = [
            e
            for e in self._entries
            if e["deadline_ts"] > now and e["used"] < self._cap
        ]
        if account:
            bound = self._bindings.get(account)
            if bound is not None:
                entry = next(
                    (e for e in self._entries if e["proxy"] == bound), None
                )
                if entry is not None:
                    entry["used"] += 1
                    return entry["proxy"]
                self._bindings.pop(account, None)
        if not self._entries and self._api_url:
            try:
                self._refill()
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                return None
        if not self._entries:
            return None
        if self._random:
            entry = random.choice(self._entries)
        else:
            entry = self._entries[self._index % len(self._entries)]
            self._index += 1
        entry["used"] += 1
        if account:
            self._bindings[account] = entry["proxy"]
        return entry["proxy"]

    def mark_failed(self, proxy: str) -> None:
        self._entries = [e for e in self._entries if e["proxy"] != proxy]
        self._bindings = {
            acc: p for acc, p in self._bindings.items() if p != proxy
        }

    def mask(self, proxy: str) -> str:
        return mask_proxy(proxy)


def load_proxy_config() -> dict:
    default = {
        "enabled": False,
        "api_url": "",
        "per_ip_cap": 8,
        "delay_min": 30,
        "delay_max": 90,
        "random": True,
    }
    try:
        data = json.loads(proxy_config_path().read_text(encoding="utf-8"))
        for key in default:
            data.setdefault(key, default[key])
        return data
    except Exception:
        return default


def save_proxy_config(config: dict) -> None:
    path = proxy_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
