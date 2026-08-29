from __future__ import annotations

from emailhub.icloud_hme import ICloudHmeClient

from .database import Database


class AppleService:
    def __init__(self, db: Database):
        self.db = db
        self.last_error = ""

    @property
    def configured(self) -> bool:
        return bool(self.db.get_setting("apple_cookie", ""))

    @property
    def region(self) -> str:
        return self.db.get_setting("apple_region", "global") or "global"

    def _client(self) -> ICloudHmeClient:
        cookie = self.db.get_setting("apple_cookie", "")
        if not cookie:
            raise RuntimeError("请先配置有效的 Apple 网页会话")
        return ICloudHmeClient(cookie, region=self.region)

    def configure(self, cookie: str, region: str) -> int:
        client = ICloudHmeClient(cookie, region=region)
        result = client.validate()
        self.db.set_setting("apple_cookie", cookie, encrypted=True)
        self.db.set_setting("apple_region", region)
        self.last_error = ""
        return len(result.get("hmeEmails") or [])

    def create_alias(self, label: str, note: str = "") -> str:
        client = self._client()
        address = client.generate()
        client.reserve(address, label, note)
        return address

    def apply_lifecycle(self, address: str, action: str) -> None:
        client = self._client()
        if action == "delete":
            client.delete_alias(address)
        elif action == "deactivate":
            client.deactivate_alias(address)
