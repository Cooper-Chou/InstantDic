"""Start-with-Windows via the per-user Run registry key (no admin rights needed)."""
import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "InstantDic"


def command():
    if getattr(sys, "frozen", False):  # packaged exe
        return f'"{sys.executable}"'
    # dev checkout: pythonw + the launcher script next to the app package
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instantdic.pyw")
    return f'"{exe}" "{script}"'


def is_enabled(value=VALUE):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, value)
            return True
    except OSError:
        return False


def set_enabled(on, value=VALUE):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, value, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, value)
            except FileNotFoundError:
                pass
