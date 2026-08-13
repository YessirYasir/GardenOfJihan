from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
import uuid
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


class MacOSKeychain:
    """Minimal Security.framework wrapper for the current user's login Keychain."""

    _ITEM_NOT_FOUND = -25300

    def __init__(self, security=None, core_foundation=None):
        if sys.platform != "darwin" and security is None:
            raise RuntimeError("Protected publishing credentials require macOS")
        self.security = security or ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/Security.framework/Security"
        )
        self.core_foundation = core_foundation or ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        self._configure_functions()

    def _configure_functions(self) -> None:
        self.security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
        self.security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
        self.security.SecKeychainItemModifyContent.restype = ctypes.c_int32
        self.security.SecKeychainItemDelete.restype = ctypes.c_int32
        self.security.SecKeychainItemFreeContent.restype = ctypes.c_int32
        self.core_foundation.CFRelease.argtypes = [ctypes.c_void_p]

    @staticmethod
    def _encoded(value: str) -> bytes:
        return value.encode("utf-8")

    @staticmethod
    def _raise(status: int, action: str) -> None:
        if status:
            raise OSError(status, f"macOS Keychain could not {action}")

    def _find(self, service: str, account: str) -> tuple[int, bytes, ctypes.c_void_p]:
        service_bytes = self._encoded(service)
        account_bytes = self._encoded(account)
        length = ctypes.c_uint32()
        data = ctypes.c_void_p()
        item = ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(
            None,
            len(service_bytes),
            service_bytes,
            len(account_bytes),
            account_bytes,
            ctypes.byref(length),
            ctypes.byref(data),
            ctypes.byref(item),
        )
        if status == self._ITEM_NOT_FOUND:
            return status, b"", item
        self._raise(status, "read protected credentials")
        try:
            value = ctypes.string_at(data, length.value)
        finally:
            self.security.SecKeychainItemFreeContent(None, data)
        return status, value, item

    def read(self, service: str, account: str) -> bytes:
        status, value, item = self._find(service, account)
        if status == self._ITEM_NOT_FOUND:
            raise FileNotFoundError("Protected macOS credential was not found")
        try:
            return value
        finally:
            if item:
                self.core_foundation.CFRelease(item)

    def write(self, service: str, account: str, value: bytes) -> None:
        status, _current, item = self._find(service, account)
        if status == self._ITEM_NOT_FOUND:
            service_bytes = self._encoded(service)
            account_bytes = self._encoded(account)
            created_item = ctypes.c_void_p()
            status = self.security.SecKeychainAddGenericPassword(
                None,
                len(service_bytes),
                service_bytes,
                len(account_bytes),
                account_bytes,
                len(value),
                value,
                ctypes.byref(created_item),
            )
            try:
                self._raise(status, "store protected credentials")
            finally:
                if created_item:
                    self.core_foundation.CFRelease(created_item)
            return
        try:
            status = self.security.SecKeychainItemModifyContent(item, None, len(value), value)
            self._raise(status, "update protected credentials")
        finally:
            if item:
                self.core_foundation.CFRelease(item)

    def delete(self, service: str, account: str) -> None:
        status, _value, item = self._find(service, account)
        if status == self._ITEM_NOT_FOUND:
            return
        try:
            self._raise(self.security.SecKeychainItemDelete(item), "delete protected credentials")
        finally:
            if item:
                self.core_foundation.CFRelease(item)


class MacOSKeychainProtector:
    """Keep OAuth material in macOS Keychain; the local file holds only a reference."""

    _SERVICE = "com.gardenofjihan.youtube-publishing"
    _MARKER = b"garden-of-jihan-keychain-v1:"

    def __init__(self, account: str, keychain: MacOSKeychain | None = None):
        self.account = account
        self.keychain = keychain or MacOSKeychain()

    @classmethod
    def for_path(cls, path: Path) -> MacOSKeychainProtector:
        identifier = hashlib.sha256(str(path.expanduser().resolve()).encode()).hexdigest()
        return cls(f"youtube-{identifier[:32]}")

    def protect(self, value: bytes) -> bytes:
        self.keychain.write(self._SERVICE, self.account, value)
        return self._MARKER + self.account.encode("ascii")

    def unprotect(self, value: bytes) -> bytes:
        expected = self._MARKER + self.account.encode("ascii")
        if value != expected:
            raise ValueError("Protected macOS credential reference is invalid")
        return self.keychain.read(self._SERVICE, self.account)

    def clear(self) -> None:
        self.keychain.delete(self._SERVICE, self.account)


def _default_protector(path: Path) -> Protector:
    if os.name == "nt":
        return WindowsDataProtector()
    if sys.platform == "darwin":
        return MacOSKeychainProtector.for_path(path)
    raise RuntimeError("Protected publishing credentials require Windows or macOS")


@lru_cache(maxsize=1)
def credential_protection_available() -> bool:
    protector: Protector | None = None
    try:
        if os.name == "nt":
            protector = WindowsDataProtector()
        elif sys.platform == "darwin":
            protector = MacOSKeychainProtector(f"health-{uuid.uuid4().hex}")
        else:
            return False
        protected = protector.protect(b"Garden of Jihan credential check")
        return protector.unprotect(protected) == b"Garden of Jihan credential check"
    except (OSError, RuntimeError, ValueError):
        return False
    finally:
        clear = getattr(protector, "clear", None)
        if clear is not None:
            try:
                clear()
            except OSError:
                pass


class ProtectedJsonStore:
    def __init__(self, path: Path, protector: Protector | None = None):
        self.path = path
        self.protector = protector or _default_protector(path)

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
        clear = getattr(self.protector, "clear", None)
        if clear is not None:
            clear()
