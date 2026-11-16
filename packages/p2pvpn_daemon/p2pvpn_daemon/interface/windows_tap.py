"""Windows TAP backend: TAP-Windows6 (tap0901) via CreateFile/DeviceIoControl.

Reading runs in a dedicated thread; frames are delivered to asyncio via
call_soon_threadsafe. OS configuration is delegated to an injected
SystemConfigurator.
"""
from __future__ import annotations

import asyncio
import logging
import struct
import threading
from typing import Callable, Optional

from p2pvpn_common.constants import MAX_FRAME
from p2pvpn_common.errors import InterfaceError
from p2pvpn_daemon.configurator.base import SystemConfigurator
from p2pvpn_daemon.interface.base import L2Interface

log = logging.getLogger("p2pvpn.interface.windows")


class WindowsTAP(L2Interface):
    COMPONENT_ID = "tap0901"
    ADAPTER_KEY = (r"SYSTEM\CurrentControlSet\Control\Class"
                   r"\{4D36E972-E325-11CE-BFC1-08002BE10318}")
    CONNECTIONS_KEY = (r"SYSTEM\CurrentControlSet\Control\Network"
                       r"\{4D36E972-E325-11CE-BFC1-08002BE10318}")

    def __init__(self, name: str, ip: str, prefix: int, mtu: int,
                 configurator: SystemConfigurator):
        self.name = name
        self.ip = ip
        self.prefix = prefix
        self.mtu = mtu
        self._configurator = configurator
        self._handle = None
        self._guid: Optional[str] = None
        self._friendly: Optional[str] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._on_frame: Optional[Callable[[bytes], None]] = None

    @staticmethod
    def _ctl(dev_type: int, fn: int) -> int:
        return (dev_type << 16) | (fn << 2)

    def _find_adapter(self, preferred_name: Optional[str] = None):
        """Scan registry for the first TAP-Windows6 adapter;
        if preferred_name is given, match it exactly."""
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, self.ADAPTER_KEY) as root:
            i = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(root, sub_name) as sub:
                        try:
                            cid = winreg.QueryValueEx(sub, "ComponentId")[0]
                        except FileNotFoundError:
                            continue
                        if cid != self.COMPONENT_ID:
                            continue
                        guid = winreg.QueryValueEx(sub, "NetCfgInstanceId")[0]
                        conn_path = f"{self.CONNECTIONS_KEY}\\{guid}\\Connection"
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, conn_path) as conn:
                            name = winreg.QueryValueEx(conn, "Name")[0]
                        if preferred_name and name != preferred_name:
                            continue
                        return guid, name
                except OSError:
                    continue
        raise InterfaceError(
            "TAP-Windows6 adapter not found. Install the driver from "
            "OpenVPN (https://build.openvpn.net/downloads/releases/) "
            "or run `tapctl.exe create`."
        )

    def setup(self) -> None:
        import win32file  # pywin32

        preferred = None if self.name in ("tap0", "") else self.name
        self._guid, self._friendly = self._find_adapter(preferred)
        log.info("Windows TAP adapter: %s  guid=%s", self._friendly, self._guid)

        device_path = rf"\\.\Global\{self._guid}.tap"
        try:
            self._handle = win32file.CreateFile(
                device_path,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                win32file.FILE_ATTRIBUTE_SYSTEM | win32file.FILE_FLAG_OVERLAPPED,
                None,
            )
        except Exception as exc:
            raise InterfaceError(f"Cannot open TAP device: {exc}") from exc

        # TAP_WIN_IOCTL_SET_MEDIA_STATUS = CTL_CODE(34, 6) — «соединить кабель»
        win32file.DeviceIoControl(
            self._handle, self._ctl(34, 6), struct.pack("I", 1), 4, None
        )
        log.info("Windows TAP media status → connected")

        self._configurator.configure(self._friendly, self.ip, self.prefix, self.mtu)
        self.name = self._friendly

    def teardown(self) -> None:
        import win32file

        self._stop.set()
        if self._handle is not None:
            try:
                win32file.DeviceIoControl(
                    self._handle, self._ctl(34, 6), struct.pack("I", 0), 4, None
                )
            except Exception:
                pass
            try:
                win32file.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)
        log.info("Windows TAP %s torn down", self._friendly or self.name)

    def write(self, frame: bytes) -> None:
        import win32file
        import pywintypes

        overlapped = pywintypes.OVERLAPPED()
        try:
            win32file.WriteFile(self._handle, frame, overlapped)
            win32file.GetOverlappedResult(self._handle, overlapped, True)
        except pywintypes.error as exc:
            log.warning("TAP write error: %s", exc)

    def start_reading(self, loop: asyncio.AbstractEventLoop,
                      on_frame: Callable[[bytes], None]) -> None:
        self._loop = loop
        self._on_frame = on_frame
        self._reader_thread = threading.Thread(
            target=self._read_loop, name="tap-win-reader", daemon=True
        )
        self._reader_thread.start()
        log.debug("Windows TAP reader thread started")

    def _read_loop(self) -> None:
        import win32file
        import win32event
        import pywintypes

        overlapped = pywintypes.OVERLAPPED()
        overlapped.hEvent = win32event.CreateEvent(None, False, False, None)
        buf = win32file.AllocateReadBuffer(MAX_FRAME)

        while not self._stop.is_set():
            try:
                win32file.ReadFile(self._handle, buf, overlapped)
                n = win32file.GetOverlappedResult(self._handle, overlapped, True)
                if n and not self._stop.is_set():
                    frame = bytes(buf[:n])
                    self._loop.call_soon_threadsafe(self._on_frame, frame)
            except pywintypes.error as exc:
                # 995 = ERROR_OPERATION_ABORTED (handle closed),
                # 6 = invalid handle. Both mean "we are shutting down".
                if exc.winerror in (995, 6) or self._stop.is_set():
                    return
                log.error("TAP read error: %s", exc)
                return
