"""User configuration, stored as JSON under %LOCALAPPDATA%\\CustomDic (never inside OneDrive)."""
import copy
import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# CUSTOMDIC_DATA_DIR lets tests run against a throwaway folder instead of the user's real data.
DATA_DIR = Path(os.environ.get("CUSTOMDIC_DATA_DIR")
                or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CustomDic")
LOG_DIR = DATA_DIR / "logs"
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULTS = {
    "hotkey": "Ctrl+F12",
    "theme": "system",         # "system" / "light" / "dark"
    # Result sections in display order: dictionaries ({"id","type":"mdx","name","path","enabled","collapsed"})
    # and built-in sources (BUILTIN_SOURCES), all reorderable in the Console.
    "sources": [],
    "ai": {
        "base_url": "https://api.deepseek.com",
        "model": "",           # empty = auto-pick the "flash" model from GET /models on first use
        "show_button": True,   # show a manual "AI 翻译" link when dictionaries did find the word
    },
    "popup": {
        "width": 520,          # logical px (DPI-independent)
        "height": 640,
        "mode": "cursor",      # "cursor" = screen under the mouse, "fixed" = screen_id
        "screen_id": "",
        "anchor": "top",       # see screens.ANCHORS
        "margin": 40,
        "hide_on_blur": True,
        "stay_on_top": True,
    },
}


# Built-in result sections; ensured present in config["sources"] so the user can reorder them.
BUILTIN_SOURCES = [
    {"id": "thesaurus", "type": "builtin", "name": "近义词 / 反义词", "enabled": True, "collapsed": False},
    {"id": "examples", "type": "builtin", "name": "例句（Tatoeba）", "enabled": True, "collapsed": False},
    {"id": "wiki", "type": "builtin", "name": "维基百科", "enabled": True, "collapsed": False},
    {"id": "ai", "type": "ai", "name": "AI 翻译（DeepSeek）", "enabled": True, "collapsed": False},
]


def _merge(base, override):
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = Path(path)
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = _merge(DEFAULTS, json.load(f))
        except FileNotFoundError:
            pass
        except Exception:
            log.exception("config.json is unreadable, falling back to defaults")
        ids = {s["id"] for s in self.data["sources"]}
        for b in BUILTIN_SOURCES:
            if b["id"] not in ids:
                # New built-ins go before AI so the AI fallback stays last by default.
                sources = self.data["sources"]
                pos = next((i for i, s in enumerate(sources) if s["id"] == "ai"), len(sources))
                sources.insert(pos, copy.deepcopy(b))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    @property
    def popup(self):
        return self.data["popup"]
