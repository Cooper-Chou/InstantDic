"""The quick-lookup popup window."""
import json
import logging
import time

from PySide6.QtCore import QEvent, QPoint, QSize, QStringListModel, Qt, QTimer, QUrl, QUrlQuery, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QCompleter, QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton, QVBoxLayout, QWidget

from . import winevents
from .i18n import tr
from .theme import THEMES
from .web import ResultPage, result_url

log = logging.getLogger(__name__)

EDGE = 5  # px of window margin used as resize handle
SUGGEST_DEBOUNCE_MS = 150


class _Grip(QLabel):
    """Drag handle: moves the window with the native move loop (DPI-correct across monitors)."""

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.window().windowHandle().startSystemMove()


class PopupWindow(QWidget):
    userResized = Signal(QSize)
    broken = Signal()  # geometry could not be fixed; owner should recreate the window

    def __init__(self, cfg, screens, engine, ai, sections, theme_name, profile):
        flags = Qt.Window | Qt.FramelessWindowHint | Qt.Tool
        if cfg.popup.get("stay_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.cfg, self.screens, self.engine, self.ai = cfg, screens, engine, ai
        self.sections = sections
        self._ai_rid = None
        self._ai_state = None
        self._sec_state = None  # {"q": query, "items": {source id: html}}
        self.setWindowTitle("InstantDic")
        # Opaque window: translucent top-levels and Chromium don't mix well. The EDGE-wide
        # margin around the card is the resize handle; Win11 DWM adds the rounded border.
        self.setObjectName("popup")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setMouseTracking(True)
        self._expected = None       # (screen, QRect) from last placement
        self._fix_attempts = 0
        self._user_resizing = False
        self._shown_at = 0.0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(EDGE, 0, EDGE, EDGE)
        card = QFrame(objectName="card")
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QFrame(objectName="header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.setSpacing(4)
        grip = _Grip("⠿", objectName="grip")
        grip.setCursor(Qt.SizeAllCursor)
        grip.setToolTip(tr("拖动窗口"))
        self.back = QToolButton(text="←", toolTip=tr("后退 (Alt+←)"))
        self.input = QLineEdit(placeholderText=tr("输入单词或句子，回车查询"))
        self.input.returnPressed.connect(self._on_submit)
        self.input.textEdited.connect(lambda _: self._suggest_timer.start())
        self.pin = QToolButton(text="📌", checkable=True, toolTip=tr("固定窗口（失焦不隐藏）"))
        for wdg, stretch in ((grip, 0), (self.back, 0), (self.input, 1), (self.pin, 0)):
            hl.addWidget(wdg, stretch)
        lay.addWidget(header)

        # Suggestions: only refresh after typing pauses for SUGGEST_DEBOUNCE_MS.
        self._suggest_model = QStringListModel(self)
        self.completer = QCompleter(self._suggest_model, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.completer.setMaxVisibleItems(10)
        self.completer.activated.connect(self._on_suggestion)
        self.input.setCompleter(self.completer)
        self._suggest_timer = QTimer(self, singleShot=True, interval=SUGGEST_DEBOUNCE_MS)
        self._suggest_timer.timeout.connect(self._refresh_suggestions)

        self.view = QWebEngineView()
        self.page = ResultPage(profile, self.view)
        self.view.setPage(self.page)
        self.view.urlChanged.connect(self._on_url_changed)
        self.view.loadFinished.connect(lambda _ok: (self._push_ai(), self._push_sections()))
        ai.update.connect(self._on_ai_update)
        sections.ready.connect(self._on_section_ready)
        self.back.clicked.connect(self.view.back)
        lay.addWidget(self.view, 1)
        self.apply_theme(theme_name)
        # Pre-warm Chromium now so the first hotkey press shows instantly.
        self.view.load(QUrl("mdict://app/home"))

        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.hide_popup)
        QShortcut(QKeySequence("Alt+Left"), self, activated=self.view.back)
        QShortcut(QKeySequence("Alt+Right"), self, activated=self.view.forward)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=lambda: (self.input.setFocus(), self.input.selectAll()))

        self._resize_save = QTimer(self, singleShot=True, interval=400)
        self._resize_save.timeout.connect(self._emit_user_resize)

    def apply_theme(self, name):
        self.page.setBackgroundColor(QColor(THEMES[name]["bg"]))

    # ---------- show / hide ----------
    def toggle(self, t0=None):
        if self.isVisible() and self.isActiveWindow():
            self.hide_popup()
        else:
            self.show_popup(t0)

    def show_popup(self, t0=None):
        t0 = t0 or time.perf_counter()
        if not self.isVisible():
            self.place()
        self.show()
        self.raise_()
        self.activateWindow()
        winevents.round_corners(self.winId())
        if not winevents.force_foreground(self.winId()):
            log.info("foreground refused, retrying")
            QTimer.singleShot(60, self._retry_foreground)
        self.input.setFocus()
        self.input.selectAll()
        self._shown_at = time.perf_counter()
        log.info("popup shown in %.0f ms", (self._shown_at - t0) * 1000)
        self._fix_attempts = 0
        QTimer.singleShot(80, self._verify)

    def _retry_foreground(self):
        if self.isVisible() and not winevents.is_foreground(self.winId()):
            ok = winevents.force_foreground(self.winId())
            log.info("foreground retry %s", "ok" if ok else "failed")
            self.activateWindow()
            self.input.setFocus()

    def hide_popup(self):
        self.completer.popup().hide()
        self.hide()

    # ---------- geometry ----------
    def place(self):
        screen, rect = self.screens.compute_geometry(self.cfg.popup)
        wh = self.windowHandle()
        if wh is None:
            self.winId()
            wh = self.windowHandle()
        # Move to the target screen first so Qt applies that screen's DPI before sizing.
        if wh.screen() is not screen:
            wh.setScreen(screen)
        self.setGeometry(rect)
        self._expected = (screen, rect)
        log.debug("placed on %s at %s", screen.name(), rect)

    def _verify(self):
        """Catch Windows/Qt applying a stale DPI or dropping us on the wrong screen."""
        if not self.isVisible() or self._expected is None:
            return
        screen, rect = self._expected
        g = self.geometry()
        ok_size = abs(g.width() - rect.width()) <= 4 and abs(g.height() - rect.height()) <= 4
        ok_screen = self.screen() is screen
        if ok_size and ok_screen:
            return
        self._fix_attempts += 1
        log.warning("popup geometry off (attempt %d): got %s on %s, expected %s on %s",
                    self._fix_attempts, g, self.screen().name(), rect, screen.name())
        if self._fix_attempts <= 2:
            self.place()
            QTimer.singleShot(80, self._verify)
        else:
            self.broken.emit()

    def on_screens_settled(self):
        """Display layout changed (sleep/wake, monitor on/off). Re-anchor if visible."""
        if self.isVisible():
            self.place()
            self._fix_attempts = 0
            QTimer.singleShot(80, self._verify)

    # ---------- edge resizing ----------
    def _edges_at(self, pos: QPoint):
        r = self.rect()
        edges = Qt.Edges()
        if pos.x() <= EDGE:
            edges |= Qt.LeftEdge
        if pos.x() >= r.width() - EDGE:
            edges |= Qt.RightEdge
        if pos.y() >= r.height() - EDGE:
            edges |= Qt.BottomEdge
        return edges

    def mouseMoveEvent(self, e):
        edges = self._edges_at(e.position().toPoint())
        cursors = {
            Qt.LeftEdge: Qt.SizeHorCursor, Qt.RightEdge: Qt.SizeHorCursor, Qt.BottomEdge: Qt.SizeVerCursor,
            Qt.RightEdge | Qt.BottomEdge: Qt.SizeFDiagCursor, Qt.LeftEdge | Qt.BottomEdge: Qt.SizeBDiagCursor,
        }
        self.setCursor(cursors.get(edges, Qt.ArrowCursor))

    def mousePressEvent(self, e):
        edges = self._edges_at(e.position().toPoint())
        if e.button() == Qt.LeftButton and edges:
            self._user_resizing = True
            self.windowHandle().startSystemResize(edges)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._user_resizing:
            self._resize_save.start()

    def _emit_user_resize(self):
        self._user_resizing = False
        self.userResized.emit(self.size())

    # ---------- focus ----------
    def changeEvent(self, e):
        super().changeEvent(e)
        if (e.type() == QEvent.ActivationChange and not self.isActiveWindow() and self.isVisible()
                and not self.pin.isChecked() and not self._user_resizing
                and self.cfg.popup.get("hide_on_blur", True)
                and time.perf_counter() - self._shown_at > 0.3):
            QTimer.singleShot(0, self._hide_if_still_inactive)

    def _hide_if_still_inactive(self):
        # The suggestion list is its own window; clicking it must not hide the popup.
        if not self.isActiveWindow() and not self.completer.popup().isVisible():
            self.hide_popup()

    # ---------- lookup ----------
    def _refresh_suggestions(self):
        text = self.input.text().strip()
        items = self.engine.suggest(text) if text else []
        self._suggest_model.setStringList(items)
        if items and self.input.hasFocus():
            self.completer.complete()
        else:
            self.completer.popup().hide()

    def _on_suggestion(self, text):
        self.input.setText(text)
        self.lookup(text)

    def _on_submit(self):
        self._suggest_timer.stop()
        self.completer.popup().hide()
        self.lookup(self.input.text())

    def lookup(self, text):
        q = text.strip()
        if q:
            self.view.load(result_url(q))
            self.input.selectAll()

    def _on_url_changed(self, url):
        # Keep the input in sync when navigating via links or back/forward.
        if url.host() == "app" and url.path() == "/result":
            q = QUrlQuery(url).queryItemValue("q", QUrl.FullyDecoded)
            if q and q != self.input.text():
                self.input.setText(q)
                self.input.selectAll()
        self.back.setEnabled(self.view.history().canGoBack())

    def reload_results(self):
        self.view.reload()

    # ---------- AI fallback ----------
    def start_ai(self, q):
        """Called when a result page needs an AI translation (dictionary miss or AI button)."""
        if self._ai_state and self._ai_state["q"] == q and self._ai_state["state"] in ("thinking", "streaming"):
            return  # same query already streaming (e.g. page reloaded)
        if self._ai_rid is not None:
            self.ai.cancel(self._ai_rid)
        self._ai_state = {"q": q, "text": "", "state": "thinking", "err": ""}
        self._ai_rid = self.ai.translate(q)

    def _on_ai_update(self, rid, text, state, err):
        if rid != self._ai_rid:
            return
        self._ai_state.update(text=text, state=state, err=err)
        self._push_ai()

    def _showing(self, q):
        url = self.view.url()
        return url.host() == "app" and QUrlQuery(url).queryItemValue("q", QUrl.FullyDecoded).strip() == q

    # ---------- examples / thesaurus / wikipedia ----------
    def start_sections(self, q, word, sids):
        if not self._sec_state or self._sec_state["q"] != q:
            self._sec_state = {"q": q, "items": {}}
        self.sections.fetch(q, word, sids)

    def _on_section_ready(self, q, sid, html):
        if self._sec_state and self._sec_state["q"] == q:
            self._sec_state["items"][sid] = html
            self._push_sections()

    def _push_sections(self):
        st = self._sec_state
        if not st or not st["items"] or not self._showing(st["q"]):
            return
        calls = ";".join(f"setSection({json.dumps(sid)},{json.dumps(h)})" for sid, h in st["items"].items())
        self.page.runJavaScript(f"if(window.setSection){{{calls}}}")

    def _push_ai(self):
        st = self._ai_state
        if not st or not self._showing(st["q"]):
            return
        args = ",".join(json.dumps(st[k]) for k in ("text", "state", "err"))
        self.page.runJavaScript(f"window.aiSet&&aiSet({args})")
