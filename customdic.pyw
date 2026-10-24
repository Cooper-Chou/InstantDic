"""Launcher: double-click (or used by autostart / PyInstaller) to run CustomDic without a console."""
import sys

from app.main import main

sys.exit(main())
