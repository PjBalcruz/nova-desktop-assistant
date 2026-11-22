"""Controls windows of apps listed in nova.toml: switch, minimize, maximize, restore, close."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

import psutil

from app.automation.app_manager import OpenResult, find_app
from app.config import NovaConfig

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.IsZoomed.restype = wintypes.BOOL
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80
DWMWA_CLOAKED = 14
SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 3, 6, 9
WM_CLOSE = 0x0010
VK_MENU = 0x12  # the Alt key
KEYEVENTF_KEYUP = 0x0002


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    process: str


def _process_name(pid: int, cache: dict[int, str]) -> str:
    if pid not in cache:
        try:
            cache[pid] = psutil.Process(pid).name()
        except psutil.Error:
            cache[pid] = ""
    return cache[pid]


def list_windows() -> list[WindowInfo]:
    """Real top-level windows, frontmost first."""
    found: list[WindowInfo] = []
    names: dict[int, str] = {}

    @WNDENUMPROC
    def on_window(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindow(hwnd, GW_OWNER):  # owned pop-ups aren't main windows
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        cloaked = wintypes.DWORD(0)  # hidden by Windows (e.g. suspended apps)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        found.append(WindowInfo(int(hwnd), buffer.value, pid.value, _process_name(pid.value, names)))
        return True

    user32.EnumWindows(on_window, 0)
    return found


def _wait_until(check: Callable[[], bool], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.1)
    return check()


def _own_process_names() -> set[str]:
    """Programs NOVA is running inside (terminal, VS Code...). NOVA never closes those."""
    try:
        return {p.name().lower() for p in psutil.Process().parents()}
    except psutil.Error:
        return set()


def _is_running(process_name: str) -> bool:
    wanted = process_name.lower()
    return any((p.info["name"] or "").lower() == wanted for p in psutil.process_iter(["name"]))


def _apply(action: str, hwnds: list[int], name: str) -> OpenResult:
    """Minimize, maximize or restore, then check that it really happened."""
    if action == "minimize":
        for h in hwnds:
            user32.ShowWindow(h, SW_MINIMIZE)
        ok = _wait_until(lambda: all(user32.IsIconic(h) for h in hwnds))
        return OpenResult(ok, f"{name} is minimized." if ok else f"I tried to minimize {name}, but it didn't minimize.")
    if action == "maximize":
        user32.ShowWindow(hwnds[0], SW_MAXIMIZE)
        ok = _wait_until(lambda: bool(user32.IsZoomed(hwnds[0])))
        return OpenResult(ok, f"{name} is maximized." if ok else f"I tried to maximize {name}, but it didn't change.")
    user32.ShowWindow(hwnds[0], SW_RESTORE)
    ok = _wait_until(lambda: not user32.IsIconic(hwnds[0]))
    return OpenResult(ok, f"{name} is restored." if ok else f"I tried to restore {name}, but it is still minimized.")


def _switch(hwnd: int, name: str) -> OpenResult:
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    # Windows only lets a program take focus right after a key press, so tap Alt first.
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(hwnd)
    if _wait_until(lambda: user32.GetForegroundWindow() == hwnd, 1.5):
        return OpenResult(True, f"You're on {name}.")
    return OpenResult(False, f"I tried, but Windows wouldn't let {name} come to the front.")


def _close(windows: list[WindowInfo], process_name: str, name: str) -> OpenResult:
    if process_name.lower() in _own_process_names():
        return OpenResult(False, f"I can't close {name}, because NOVA is running inside it.")
    target = windows[0]
    user32.PostMessageW(target.hwnd, WM_CLOSE, 0, 0)  # a polite request, like clicking the X
    closed = _wait_until(lambda: not user32.IsWindow(target.hwnd) or not user32.IsWindowVisible(target.hwnd))
    if not closed:
        return OpenResult(False, f"I asked {name} to close, but it's still open. It may be asking you to save something.")
    remaining = [w for w in list_windows() if w.process.lower() == process_name.lower()]
    if remaining:
        n = len(remaining)
        return OpenResult(True, f"Closed one {name} window. {n} more {'is' if n == 1 else 'are'} still open.")
    if _wait_until(lambda: not _is_running(process_name), 2.0):
        return OpenResult(True, f"{name} is closed.")
    return OpenResult(True, f"Closed the {name} window. It may still be running in the background.")


def control_window(action: str, spoken: str | None, config: NovaConfig) -> OpenResult:
    """action: switch, minimize, maximize, restore or close.
    spoken: the app name; None means the window you are using right now."""
    try:
        if not spoken:
            if action not in ("minimize", "maximize", "restore"):
                return OpenResult(False, f"Tell me which app to {action}, for example: {action} Spotify.")
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return OpenResult(False, "I can't tell which window is active.")
            return _apply(action, [int(hwnd)], "The active window")

        match = find_app(spoken, config)
        if match is None:
            return OpenResult(False, f"I don't know an app called {spoken}. You can add it to nova.toml.")
        _, entry = match
        name = entry.start_name
        if not entry.process:
            return OpenResult(False, f"I can't tell which windows belong to {name}. Add a process line for it in nova.toml.")
        wanted = entry.process.lower()
        windows = [w for w in list_windows() if w.process.lower() == wanted]
        if not windows:
            return OpenResult(False, f"{name} doesn't have an open window. Say open {spoken} to start it.")

        if action == "minimize":
            return _apply("minimize", [w.hwnd for w in windows], name)
        if action == "maximize":
            return _apply("maximize", [windows[0].hwnd], name)
        if action == "restore":
            target = next((w for w in windows if user32.IsIconic(w.hwnd)), windows[0])
            return _apply("restore", [target.hwnd], name)
        if action == "switch":
            return _switch(windows[0].hwnd, name)
        if action == "close":
            return _close(windows, entry.process, name)
        return OpenResult(False, f"I don't know how to {action} a window.")
    except Exception as exc:
        return OpenResult(False, f"I couldn't do that: {exc}")