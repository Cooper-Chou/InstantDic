"""Entry point: tray-resident process that owns the hotkey and the popup."""
import hashlib
import logging
import logging.handlers
import sys
import time

from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401  (must load before QApplication)
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import autostart, migrate, theme
from .ai import AiService
from .datasets import DATASETS, DatasetManager
from .providers import SectionService
from .config import DATA_DIR, LOG_DIR, Config, section_name
from .i18n import LANG_LABELS, first_run_default, set_language, tr
from .console import ConsoleWindow, default_name
from .dictionaries import INDEX_DIR, install_index
from .history import History
from .indexer import IndexService
from .lookup import LookupEngine
from .popup import PopupWindow
from .screens import ScreenManager
from .tray import Tray
from .web import SCHEME, SchemeHandler, register_scheme
from .winevents import SystemEvents

log = logging.getLogger("instantdic")
# One instance per data folder (a test run with INSTANTDIC_DATA_DIR doesn't collide with the real one).
INSTANCE_KEY = "InstantDic-" + hashlib.sha1(str(DATA_DIR).lower().encode("utf-8")).hexdigest()[:10]


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(LOG_DIR / "instantdic.log", maxBytes=1_000_000,
                                                   backupCount=3, encoding="utf-8")
    handlers = [handler] + ([logging.StreamHandler()] if sys.stderr else [])  # pythonw has no stderr
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class AppController:
    def __init__(self, app):
        self.app = app
        self.cfg = Config()
        if self.cfg.data.get("language") not in LANG_LABELS:  # first run, or the old "system" value
            self.cfg.data["language"] = first_run_default()
            self.cfg.save()
        set_language(self.cfg.data["language"])
        self.theme_name = theme.apply(app, self.cfg.data.get("theme", "system"))
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_scheme)

        self.engine = LookupEngine(self.cfg)
        self.history = History()
        self.indexer = IndexService()
        self.indexer.finished.connect(self._on_index_finished)
        self.profile = QWebEngineProfile.defaultProfile()
        self.ai = AiService(self.cfg)
        self.datasets = DatasetManager()
        self.datasets.finished.connect(self._on_dataset_finished)
        self.sections = SectionService(self.cfg, self.datasets)
        self.scheme_handler = SchemeHandler(self.engine, self.ai, self.sections, self.cfg, lambda: self.theme_name)
        self.scheme_handler.aiNeeded.connect(lambda q: self.popup.start_ai(q))
        self.scheme_handler.sectionsNeeded.connect(lambda q, w, ids: self.popup.start_sections(q, w, ids))
        self.profile.installUrlSchemeHandler(SCHEME, self.scheme_handler)

        self.screens = ScreenManager(app)
        self.sys = SystemEvents()
        self.popup = None
        self.console = None
        self._make_popup()

        self.sys.hotkeyPressed.connect(lambda: self.toggle_popup(time.perf_counter()))
        self.sys.environmentChanged.connect(self.screens.notify_change)
        self.screens.settled.connect(lambda: self.popup.on_screens_settled())

        self.tray = Tray(self)
        self.tray.show()
        err = self.sys.register_hotkey(self.cfg.data["hotkey"])
        if err:
            log.warning(err)
            self.tray.showMessage("InstantDic", err, QSystemTrayIcon.Warning, 8000)

        # Download free offline datasets for enabled built-in sections in the background.
        for name in ("examples", "wordnet"):
            sid = "thesaurus" if name == "wordnet" else name
            if any(s["id"] == sid and s.get("enabled", True) for s in self.cfg.data["sources"]):
                self.datasets.ensure(name)

        # Keep the autostart entry pointing at whatever packaged build is running now (installer, zip,
        # local build). Source and test runs must never rewrite the user's real autostart entry.
        try:
            if autostart.should_refresh() and autostart.is_enabled():
                autostart.set_enabled(True)
        except OSError:
            log.exception("could not refresh autostart entry")

        for src in self.engine.stale_sources():
            log.info("index missing or outdated, rebuilding: %s", src["path"])
            self.indexer.build(src)

    def _make_popup(self):
        self.popup = PopupWindow(self.cfg, self.screens, self.engine, self.ai, self.sections, self.history,
                                 self.theme_name, self.profile)
        self.popup.userResized.connect(self._save_size)
        self.popup.broken.connect(self.reset_popup)

    def _save_size(self, size: QSize):
        self.cfg.popup.update(width=size.width(), height=size.height())
        self.cfg.save()
        log.info("popup size saved: %dx%d", size.width(), size.height())

    def _on_index_finished(self, sid, title, tmp, err):
        src = next((s for s in self.cfg.data["sources"] if s["id"] == sid), None)
        if src is None:
            return
        if not err:
            self.engine.close(sid)
            try:
                install_index(tmp, INDEX_DIR / f"{sid}.sqlite")
            except OSError as e:
                log.exception("could not install index for %s", sid)
                err = str(e)
        if err:
            src["error"] = err
            self.tray.showMessage("InstantDic", tr("导入「{name}」失败：{err}", name=section_name(src), err=err), QSystemTrayIcon.Warning, 8000)
        else:
            src.pop("error", None)
            if not src.get("named_by_user"):
                src["name"] = default_name(src["path"], title)
        self.cfg.save()
        self.engine.reload()

    def _on_dataset_finished(self, name, err):
        label = tr(DATASETS[name]["label"])
        if err:
            self.tray.showMessage("InstantDic", tr("{label} 下载失败：{err}\n下次启动会重试。", label=label, err=err), QSystemTrayIcon.Warning, 8000)
        else:
            if name == "wordnet":
                self.sections.providers["thesaurus"].warm_up()
            self.sections.cache.clear()

    # ---------- theme ----------
    def set_theme(self, setting):
        self.cfg.data["theme"] = setting
        self.cfg.save()
        self._apply_theme()

    def _on_system_scheme(self, *_):
        if self.cfg.data.get("theme", "system") == "system":
            self._apply_theme()

    def _apply_theme(self):
        self.theme_name = theme.apply(self.app, self.cfg.data.get("theme", "system"))
        self.popup.apply_theme(self.theme_name)
        self.popup.reload_results()

    def set_language(self, setting):
        """Result pages and the tray menu switch now; widgets already built switch on restart."""
        self.cfg.data["language"] = setting
        self.cfg.save()
        set_language(setting)
        self.tray.setToolTip(tr("InstantDic 快捷查词"))
        self.popup.reload_results()

    # ---------- actions ----------
    def set_hotkey(self, text):
        err = self.sys.register_hotkey(text)
        if err:
            self.sys.register_hotkey(self.cfg.data["hotkey"])  # restore the previous one
            return err
        self.cfg.data["hotkey"] = text
        self.cfg.save()
        return None

    def toggle_popup(self, t0=None):
        self.popup.toggle(t0)

    def show_popup(self, query=""):
        self.popup.show_popup()
        if query:
            self.popup.input.setText(query)
            self.popup.lookup(query)

    def show_console(self):
        if self.console is None:
            self.console = ConsoleWindow(self)
        self.console.show_window()

    def reset_popup(self):
        """Destroy and rebuild the window: clears any stale per-monitor DPI state Windows kept."""
        log.warning("recreating popup window")
        was_visible = self.popup._state == "shown"
        text = self.popup.input.text()
        self.popup.hide_popup("reset")
        self.popup.deleteLater()
        self._make_popup()
        self.popup.input.setText(text)
        if was_visible:
            self.popup.show_popup()

    def quit(self):
        self.sys.unregister_hotkey()
        self.tray.hide()
        self.app.quit()


def main():
    register_scheme()
    app = QApplication(sys.argv)
    app.setApplicationName("InstantDic")
    app.setQuitOnLastWindowClosed(False)

    # Single instance: a second launch asks the running one to show the popup,
    # or to look up a word: `InstantDic.exe serendipity` (handy from AutoHotkey scripts).
    query = " ".join(sys.argv[1:]).strip()
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(query.encode("utf-8") or b"\x00")
        sock.waitForBytesWritten(300)
        return 0

    notes = migrate.run()  # before anything opens files in the data folder
    setup_logging()
    log.info("starting InstantDic")
    for note in notes:
        log.info("migration: %s", note)
    QLocalServer.removeServer(INSTANCE_KEY)
    server = QLocalServer()
    server.listen(INSTANCE_KEY)
    ctl = AppController(app)

    def on_conn():
        c = server.nextPendingConnection()
        c.readyRead.connect(lambda: ctl.show_popup(bytes(c.readAll()).decode("utf-8", "ignore").strip("\x00").strip()))

    server.newConnection.connect(on_conn)
    if query:
        ctl.show_popup(query)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
