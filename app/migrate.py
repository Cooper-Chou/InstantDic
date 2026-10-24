"""One-time migration from the project's old name (CustomDic) to InstantDic.

Moves the data folder, the API key in Windows Credential Manager and the autostart entry,
so existing users keep their dictionaries, settings and key. Safe to run on every start.
"""
import os
import shutil
from pathlib import Path

import keyring

from . import autostart
from .config import DATA_DIR

LEGACY_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CustomDic"
LEGACY_KEY = ("CustomDic", "deepseek-api-key")


def run():
    """Returns human-readable notes about what was migrated (logged by the caller)."""
    if os.environ.get("INSTANTDIC_DATA_DIR"):  # test runs use a throwaway folder
        return []
    notes = []
    for step in (_data_dir, _api_key, _autostart):
        try:
            note = step()
            if note:
                notes.append(note)
        except Exception as e:  # never block startup on a migration problem
            notes.append(f"migration step {step.__name__} failed: {e}")
    return notes


def _data_dir():
    if DATA_DIR.exists() or not LEGACY_DIR.is_dir():
        return None
    try:
        os.rename(LEGACY_DIR, DATA_DIR)
        return f"moved {LEGACY_DIR} -> {DATA_DIR}"
    except OSError:
        # The old version may still be running and holding files open: copy instead.
        shutil.copytree(LEGACY_DIR, DATA_DIR, ignore=shutil.ignore_patterns("*.building", "*.tmp", "*.part"))
        return f"copied {LEGACY_DIR} -> {DATA_DIR} (old folder was in use)"


def _api_key():
    from .ai import KEYRING_SERVICE, KEYRING_USER
    if keyring.get_password(KEYRING_SERVICE, KEYRING_USER):
        return None
    old = keyring.get_password(*LEGACY_KEY)
    if not old:
        return None
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, old)
    keyring.delete_password(*LEGACY_KEY)
    return "moved API key to the new credential entry"


def _autostart():
    if not autostart.is_enabled("CustomDic"):
        return None
    autostart.set_enabled(False, "CustomDic")
    autostart.set_enabled(True)
    return "moved autostart entry"
