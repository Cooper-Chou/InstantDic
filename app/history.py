"""Search history: most recent first, de-duplicated, stored as JSON in the data folder."""
import json
import logging
import os

from .config import DATA_DIR

log = logging.getLogger(__name__)

HISTORY_PATH = DATA_DIR / "history.json"
MAX_ITEMS = 200


class History:
    def __init__(self, path=HISTORY_PATH):
        self.path = path
        self.items = []
        try:
            with open(self.path, encoding="utf-8") as f:
                self.items = [s for s in json.load(f) if isinstance(s, str)][:MAX_ITEMS]
        except FileNotFoundError:
            pass
        except Exception:
            log.exception("history.json is unreadable, starting empty")

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=0)
        os.replace(tmp, self.path)

    def add(self, query):
        q = " ".join(query.split())
        if not q:
            return
        self.items = [q] + [s for s in self.items if s.casefold() != q.casefold()]
        del self.items[MAX_ITEMS:]
        self._save()

    def remove(self, query):
        self.items = [s for s in self.items if s != query]
        self._save()

    def clear(self):
        self.items = []
        self._save()

    def matching(self, prefix, limit=5):
        p = prefix.strip().casefold()
        return [s for s in self.items if s.casefold().startswith(p)][:limit] if p else []
