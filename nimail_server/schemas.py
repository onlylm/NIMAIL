from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class BootstrapRequest(BaseModel):
    bootstrap_token: str = Field(min_length=32, max_length=256)
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.\-\u4e00-\u9fff]+", value):
            raise ValueError("管理员名称只能包含中英文、数字、点、横线和下划线")
        return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class DeploymentConfigureRequest(BaseModel):
    domain: str = Field(min_length=4, max_length=253)


class MailboxCreateRequest(BaseModel):
    address: str = Field(min_length=5, max_length=254)
    service_name: str = Field(default="", max_length=100)
    cdk: str | None = Field(default=None, min_length=8, max_length=128)
    deactivate_after_seconds: int | None = Field(default=1800, ge=0, le=315360000)
    message_retention_seconds: int | None = Field(default=86400, ge=0, le=315360000)
    cdk_retention_seconds: int | None = Field(default=86400, ge=0, le=315360000)
    apple_action: Literal["keep", "deactivate", "delete"] = "deactivate"

    @field_validator("address")
    @classmethod
    def clean_address(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("请输入有效邮箱地址")
        return value

    @field_validator("cdk")
    @classmethod
    def clean_cdk(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class PolicyUpdateRequest(BaseModel):
    deactivate_after_seconds: int | None = Field(default=None, ge=0, le=315360000)
    message_retention_seconds: int | None = Field(default=None, ge=0, le=315360000)
    cdk_retention_seconds: int | None = Field(default=None, ge=0, le=315360000)
    apple_action: Literal["keep", "deactivate", "delete"] = "deactivate"


class ImapConfigureRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    app_password: str = Field(min_length=4, max_length=128)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("请输入有效的 iCloud 邮箱")
        return value


class AppleConfigureRequest(BaseModel):
    cookie: str = Field(min_length=20, max_length=65535)
    region: Literal["global", "china"] = "global"


class AppleCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=500)
    cdk: str | None = Field(default=None, min_length=8, max_length=128)
    deactivate_after_seconds: int | None = Field(default=1800, ge=0, le=315360000)
    message_retention_seconds: int | None = Field(default=86400, ge=0, le=315360000)
    cdk_retention_seconds: int | None = Field(default=86400, ge=0, le=315360000)
    apple_action: Literal["keep", "deactivate", "delete"] = "deactivate"

    @field_validator("label", "note")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()


class AppleBatchCreateRequest(BaseModel):
    count: int = Field(ge=1, le=20)
    label_prefix: str = Field(default="隐藏邮箱", min_length=1, max_length=80)
    note: str = Field(default="", max_length=500)
    interval_seconds: int = Field(default=30, ge=5, le=300)
    deactivate_after_seconds: int | None = Field(default=1800, ge=0, le=315360000)
    message_retention_seconds: int | None = Field(default=86400, ge=0, le=315360000)
    cdk_retention_seconds: int | None = Field(default=86400, ge=0, le=315360000)
    apple_action: Literal["keep", "deactivate", "delete"] = "deactivate"

    @field_validator("label_prefix", "note")
    @classmethod
    def clean_batch_text(cls, value: str) -> str:
        return value.strip()
