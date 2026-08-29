from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class ApiError(RuntimeError):
    pass


def normalize_server_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if "://" not in value:
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiError("服务器地址格式不正确")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ApiError("远程服务器必须使用 HTTPS")
    return value


def validate_apple_cookie(value: str) -> str:
    cookie = value.strip()
    if len(cookie) < 20:
        raise ApiError("请粘贴完整的 iCloud Cookie")
    if "X-APPLE-WEBAUTH-USER=" not in cookie:
        raise ApiError("Cookie 缺少 X-APPLE-WEBAUTH-USER，请复制完整的 iCloud 请求 Cookie")
    return cookie


def batch_txt_lines(job: dict, fallback_base_url: str) -> list[str]:
    """生成“邮箱----CDK 取信网址”的纯文本导出行。"""
    base = normalize_server_url(fallback_base_url).rstrip("/")
    lines = []
    for item in job.get("items", []):
        address = (item.get("address") or "").strip()
        cdk = (item.get("cdk") or "").strip()
        if item.get("state") != "success" or not address or not cdk:
            continue
        viewer_url = (item.get("viewer_url") or f"{base}/c/{cdk}").strip()
        lines.append(f"{address}----{viewer_url}")
    return lines


class ApiClient:
    def __init__(self, server_url: str, token: str = ""):
        self.server_url = normalize_server_url(server_url)
        self.token = token

    def request(self, method: str, path: str, payload=None, timeout: int = 35):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(self.server_url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            try:
                data = json.loads(exc.read().decode("utf-8"))
                message = data.get("detail") or data.get("error") or str(exc)
                if isinstance(message, list):
                    message = "；".join(item.get("msg", str(item)) for item in message)
            except Exception:
                message = str(exc)
            raise ApiError(message) from None
        except urllib.error.URLError as exc:
            raise ApiError(f"无法连接服务器：{exc.reason}") from None

    def bootstrap_status(self):
        return self.request("GET", "/api/bootstrap/status")

    def bootstrap(self, token: str, username: str, password: str):
        return self.request("POST", "/api/bootstrap", {
            "bootstrap_token": token, "username": username, "password": password,
        })

    def login(self, username: str, password: str):
        return self.request("POST", "/api/admin/login", {"username": username, "password": password})

    def status(self):
        return self.request("GET", "/api/admin/status")

    def configure_deployment(self, domain: str):
        return self.request("PUT", "/api/admin/deployment", {"domain": domain}, 60)

    def mailboxes(self):
        return self.request("GET", "/api/admin/mailboxes")

    def mailbox_messages(self, mailbox_id: str):
        return self.request("GET", f"/api/admin/mailboxes/{mailbox_id}/messages?limit=100")

    def start_batch(self, payload: dict):
        return self.request("POST", "/api/admin/apple/batch", payload, timeout=60)

    def latest_batch(self):
        return self.request("GET", "/api/admin/apple/batch/latest")

    def batch_status(self, job_id: str):
        return self.request("GET", f"/api/admin/apple/batch/{job_id}")

    def rotate_cdk(self, mailbox_id: str):
        return self.request("POST", f"/api/admin/mailboxes/{mailbox_id}/rotate-cdk", {})

    def update_policy(self, mailbox_id: str, payload: dict):
        return self.request("PUT", f"/api/admin/mailboxes/{mailbox_id}/policy", payload)

    def delete_mailbox(self, mailbox_id: str, apple_delete: bool):
        flag = "true" if apple_delete else "false"
        return self.request("DELETE", f"/api/admin/mailboxes/{mailbox_id}?apple_delete={flag}")

    def configure_imap(self, email: str, password: str):
        return self.request("POST", "/api/admin/imap/configure", {"email": email, "app_password": password}, 45)

    def sync_imap(self):
        return self.request("POST", "/api/admin/imap/sync", {}, 60)

    def configure_apple(self, cookie: str, region: str):
        return self.request("POST", "/api/admin/apple/configure", {"cookie": cookie, "region": region}, 60)
