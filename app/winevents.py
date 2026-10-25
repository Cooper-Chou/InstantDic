"""Win32 glue: global hotkey, power/display notifications, foreground activation.

A hidden native window owns the hotkey and receives broadcast messages
(WM_DISPLAYCHANGE, WM_POWERBROADCAST, ...) that Qt does not surface as signals.
"""
import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget

from .i18n import tr

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.RegisterPowerSettingNotification.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
user32.RegisterPowerSettingNotification.restype = wintypes.HANDLE
wtsapi32.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

WM_SETTINGCHANGE = 0x001A
WM_DISPLAYCHANGE = 0x007E
WM_POWERBROADCAST = 0x0218
WM_WTSSESSION_CHANGE = 0x02B1
WM_HOTKEY = 0x0312
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012
PBT_POWERSETTINGCHANGE = 0x8013
SPI_SETWORKAREA = 0x002F
WTS_SESSION_UNLOCK = 0x8
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT,
         "win": MOD_WIN, "meta": MOD_WIN}
_KEYS = {"space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
         "backspace": 0x08, "insert": 0x2D, "ins": 0x2D, "delete": 0x2E, "del": 0x2E,
         "home": 0x24, "end": 0x23, "pgup": 0x21, "pageup": 0x21, "pgdn": 0x22, "pagedown": 0x22,
         "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "pause": 0x13,
         "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
         "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF}


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, s):
        import uuid
        return cls.from_buffer_copy(uuid.UUID(s).bytes_le)


class POWERBROADCAST_SETTING(ctypes.Structure):
    _fields_ = [("PowerSetting", GUID), ("DataLength", wintypes.DWORD), ("Data", wintypes.DWORD)]


# Fires when monitors are turned off/on (screen blanking) without full system sleep.
GUID_CONSOLE_DISPLAY_STATE = GUID.parse("6FE69556-704A-47A0-8F24-C28D936FDA47")


def parse_hotkey(text):
    """'Ctrl+Alt+D' -> (modifiers, vk). Raises ValueError on unknown keys."""
    mods, vk = 0, None
    for part in [p.strip() for p in text.split("+") if p.strip()]:
        low = part.lower()
        if low in _MODS:
            mods |= _MODS[low]
        elif vk is not None:
            raise ValueError(tr("快捷键里只能有一个非修饰键：{text}", text=text))
        elif low in _KEYS:
            vk = _KEYS[low]
        elif len(low) == 1 and low.isalnum():
            vk = ord(low.upper())
        elif low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 24:
            vk = 0x70 + int(low[1:]) - 1
        else:
            raise ValueError(tr("无法识别的按键：{part}", part=part))
    if vk is None:
        raise ValueError(tr("快捷键缺少主键：{text}", text=text))
    return mods, vk


class SystemEvents(QWidget):
    """Never shown. Hidden top-level windows still receive broadcast messages."""
    hotkeyPressed = Signal()
    environmentChanged = Signal(str)  # reason

    HOTKEY_ID = 1

    def __init__(self):
        super().__init__(None, Qt.Tool)
        self.setAttribute(Qt.WA_NativeWindow)
        self.hwnd = int(self.winId())
        self._hotkey = None
        user32.RegisterPowerSettingNotification(self.hwnd, ctypes.byref(GUID_CONSOLE_DISPLAY_STATE), 0)
        wtsapi32.WTSRegisterSessionNotification(self.hwnd, 0)

    def register_hotkey(self, text):
        """Returns None on success, else a user-facing error message."""
        self.unregister_hotkey()
        try:
            mods, vk = parse_hotkey(text)
        except ValueError as e:
            return str(e)
        if not user32.RegisterHotKey(self.hwnd, self.HOTKEY_ID, mods | MOD_NOREPEAT, vk):
            err = ctypes.get_last_error()
            if err == ERROR_HOTKEY_ALREADY_REGISTERED:
                return tr("快捷键 {text} 已被其他程序占用（例如 EasyDict），请先关闭它或换一个快捷键。", text=text)
            return tr("注册快捷键 {text} 失败（错误码 {err}）。", text=text, err=err)
        self._hotkey = text
        log.info("hotkey registered: %s", text)
        return None

    def unregister_hotkey(self):
        if self._hotkey:
            user32.UnregisterHotKey(self.hwnd, self.HOTKEY_ID)
            self._hotkey = None

    def nativeEvent(self, eventType, message):
        msg = wintypes.MSG.from_address(int(message))
        m = msg.message
        if m == WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
            self.hotkeyPressed.emit()
        elif m == WM_DISPLAYCHANGE:
            self.environmentChanged.emit("WM_DISPLAYCHANGE")
        elif m == WM_SETTINGCHANGE and msg.wParam == SPI_SETWORKAREA:
            self.environmentChanged.emit("work area changed")
        elif m == WM_WTSSESSION_CHANGE and msg.wParam == WTS_SESSION_UNLOCK:
            self.environmentChanged.emit("session unlock")
        elif m == WM_POWERBROADCAST:
            if msg.wParam in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND):
                self.environmentChanged.emit("resume from sleep")
            elif msg.wParam == PBT_POWERSETTINGCHANGE and msg.lParam:
                pbs = POWERBROADCAST_SETTING.from_address(msg.lParam)
                if bytes(pbs.PowerSetting) == bytes(GUID_CONSOLE_DISPLAY_STATE):
                    state = {0: "off", 1: "on", 2: "dimmed"}.get(pbs.Data, pbs.Data)
                    self.environmentChanged.emit(f"display power {state}")
        return False, 0


def is_foreground(hwnd):
    return user32.GetForegroundWindow() == int(hwnd)


def force_foreground(hwnd):
    """SetForegroundWindow, falling back to attaching to the foreground thread's input queue."""
    hwnd = int(hwnd)
    if user32.SetForegroundWindow(hwnd):
        return True
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    cur_tid = kernel32.GetCurrentThreadId()
    if fg_tid and fg_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, True)
        try:
            user32.BringWindowToTop(hwnd)
            ok = user32.SetForegroundWindow(hwnd)
        finally:
            user32.AttachThreadInput(cur_tid, fg_tid, False)
        return bool(ok)
    return False


def round_corners(hwnd):
    """Windows 11 rounded corners for a frameless window (no-op on Windows 10)."""
    DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2
    pref = ctypes.c_int(DWMWCP_ROUND)
    dwmapi.DwmSetWindowAttribute(int(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(pref), 4)
