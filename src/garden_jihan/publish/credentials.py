from __future__ import annotations

import ctypes
import json
import os
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol


class Protector(Protocol):
    def protect(self, value: bytes) -> bytes: ...

    def unprotect(self, value: bytes) -> bytes: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


class WindowsDataProtector:
    """Encrypt OAuth material for the current Windows user with DPAPI."""

    _NO_UI = 0x1

    @staticmethod
    def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array]:
        buffer = ctypes.create_string_buffer(value)
        blob = _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        return blob, buffer

    def protect(self, value: bytes) -> bytes:
        if os.name != "nt":
            raise RuntimeError("Protected publishing credentials require Windows")
        source, source_buffer = self._blob(value)
        destination = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        success = crypt32.CryptProtectData(
            ctypes.byref(source),
            "Garden of Jihan publishing credentials",
            None,
            None,
            None,
            self._NO_UI,
            ctypes.byref(destination),
        )
        del source_buffer
        if not success:
            raise ctypes.WinError()
        try:
            return ctypes.string_at(destination.data, destination.size)
        finally:
            kernel32.LocalFree(destination.data)

    def unprotect(self, value: bytes) -> bytes:
        if os.name != "nt":
            raise RuntimeError("Protected publishing credentials require Windows")
        source, source_buffer = self._blob(value)
        destination = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        success = crypt32.CryptUnprotectData(
            ctypes.byref(source),
            None,
            None,
            None,
            None,
            self._NO_UI,
            ctypes.byref(destination),
        )
        del source_buffer
        if not success:
            raise ctypes.WinError()
        try:
            return ctypes.string_at(destination.data, destination.size)
        finally:
            kernel32.LocalFree(destination.data)


@lru_cache(maxsize=1)
def credential_protection_available() -> bool:
    try:
        protector = WindowsDataProtector()
        protected = protector.protect(b"Garden of Jihan credential check")
        return protector.unprotect(protected) == b"Garden of Jihan credential check"
    except (OSError, RuntimeError):
        return False


class ProtectedJsonStore:
    def __init__(self, path: Path, protector: Protector | None = None):
        self.path = path
        self.protector = protector or WindowsDataProtector()

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            decrypted = self.protector.unprotect(self.path.read_bytes())
            value = json.loads(decrypted.decode("utf-8"))
        except (OSError, RuntimeError, UnicodeError, ValueError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def save(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        protected = self.protector.protect(encoded)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(protected)
        temporary.replace(self.path)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
