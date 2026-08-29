from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes


CRYPTPROTECT_LOCAL_MACHINE = 0x4


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("NIMAIL 服务器凭据加密仅支持 Windows")
    source, source_buffer = _blob(data)
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "NIMAIL server secret", None, None, None,
        CRYPTPROTECT_LOCAL_MACHINE, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("NIMAIL 服务器凭据解密仅支持 Windows")
    source, source_buffer = _blob(data)
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def protect_text(value: str) -> str:
    return base64.b64encode(protect(value.encode("utf-8"))).decode("ascii")


def unprotect_text(value: str) -> str:
    if not value:
        return ""
    return unprotect(base64.b64decode(value, validate=True)).decode("utf-8")
