"""Background index builds, so importing a large dictionary never freezes the popup."""
import logging
import threading

from PySide6.QtCore import QObject, Signal

from .dictionaries import INDEX_DIR, build_index

log = logging.getLogger(__name__)


class IndexService(QObject):
    progress = Signal(str, str)             # source id, message
    finished = Signal(str, str, str, str)   # source id, title, built tmp file, error ("" on success)

    def __init__(self):
        super().__init__()
        self.running = set()

    def build(self, source):
        sid = source["id"]
        if sid in self.running:
            return
        self.running.add(sid)

        def work():
            title, tmp, err = "", "", ""
            try:
                title, tmp = build_index(source["path"], INDEX_DIR / f"{sid}.sqlite",
                                    lambda msg: self.progress.emit(sid, msg))
                log.info("indexed %s", source["path"])
            except Exception as e:
                log.exception("index build failed for %s", source["path"])
                err = str(e) or e.__class__.__name__
            self.running.discard(sid)
            self.finished.emit(sid, title, str(tmp), err)

        threading.Thread(target=work, daemon=True, name=f"index-{sid}").start()
