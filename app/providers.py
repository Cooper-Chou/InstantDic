"""Built-in non-AI result sections: example sentences, synonyms/antonyms, Wikipedia.

Each provider is a plain function (query, word) -> HTML ("" = nothing to show). They run on
a worker thread so network calls never block the popup; results come back via a Qt signal.
"""
import html
import json
import logging
import re
import sqlite3
import threading
import urllib.parse
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from . import datasets
from .ai import is_sentence

log = logging.getLogger(__name__)

TIMEOUT = 6
CJK = re.compile(r"[一-鿿]")


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": datasets.USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _word_link(w):
    return f"<a class='w' href='mdict://app/result?q={urllib.parse.quote(w, safe='')}'>{html.escape(w)}</a>"


def _downloading(name, mgr):
    if name in mgr.running:
        return f"<div class='dim'>{datasets.DATASETS[name]['label']} 正在下载，完成后即可使用。</div>"
    mgr.ensure(name)
    return f"<div class='dim'>首次使用需要下载 {datasets.DATASETS[name]['label']}（{datasets.DATASETS[name]['size']}），已开始下载。</div>"


# ---------------------------------------------------------------- examples
class Examples:
    def __init__(self, mgr, limit=6):
        self.mgr, self.limit = mgr, limit
        self._local = threading.local()

    def _db(self):
        con = getattr(self._local, "con", None)
        if con is None:
            con = self._local.con = sqlite3.connect(f"file:{datasets.EXAMPLES_DB}?mode=ro", uri=True)
        return con

    def __call__(self, q, word):
        if not datasets.is_ready("examples"):
            return _downloading("examples", self.mgr)
        if CJK.search(q):
            rows = self._db().execute(
                "SELECT eng, replace(cmn, ?, char(1) || ? || char(2)) FROM ex WHERE cmn LIKE ? "
                "ORDER BY abs(length(cmn) - 18) LIMIT ?", (q, q, f"%{q}%", self.limit)).fetchall()
        else:
            terms = " ".join('"' + t.replace('"', '""') + '"' for t in word.split())
            rows = self._db().execute(
                # Stemming also matches "happiness" for "happy": sentences with the exact form go first.
                "SELECT highlight(ex, 0, char(1), char(2)), cmn FROM ex WHERE ex MATCH ? AND length(eng) >= 18 "
                "ORDER BY instr(lower(eng), ?) = 0, abs(length(eng) - 55) LIMIT ?",
                (f"eng:({terms})", word.lower(), self.limit)).fetchall()
        if not rows:
            return ""

        def mark(s):
            return html.escape(s).replace("\x01", "<b>").replace("\x02", "</b>")

        items = "".join(f"<li><div class='en'>{mark(e)}</div><div class='zh'>{mark(c)}</div></li>" for e, c in rows)
        return f"<ol class='ex'>{items}</ol><div class='src'>例句来源：Tatoeba（CC-BY 2.0 FR）</div>"


# ---------------------------------------------------------------- thesaurus
POS_LABEL = {"n": "n.", "v": "v.", "a": "adj.", "s": "adj.", "r": "adv."}


class Thesaurus:
    def __init__(self, mgr):
        self.mgr = mgr
        self._wn = None
        self._lock = threading.Lock()

    def _wordnet(self):
        with self._lock:
            if self._wn is None:
                import nltk
                if str(datasets.NLTK_DIR) not in nltk.data.path:
                    nltk.data.path.insert(0, str(datasets.NLTK_DIR))
                from nltk.corpus import wordnet
                wordnet.ensure_loaded()
                self._wn = wordnet
            return self._wn

    def warm_up(self):
        if datasets.is_ready("wordnet"):
            threading.Thread(target=self._wordnet, daemon=True).start()

    def __call__(self, q, word):
        if CJK.search(q):
            return ""
        w = word.strip().lower()
        senses, antonyms = [], []
        wn_note = ""
        if datasets.is_ready("wordnet"):
            wn = self._wordnet()
            key = w.replace(" ", "_")
            for syn in wn.synsets(key)[:8]:
                lemmas = [l.name().replace("_", " ") for l in syn.lemmas()]
                others = [x for x in lemmas if x.lower() != w]
                for l in syn.lemmas():
                    for a in l.antonyms():
                        n = a.name().replace("_", " ")
                        if n not in antonyms:
                            antonyms.append(n)
                if others:
                    senses.append((POS_LABEL.get(syn.pos(), ""), syn.definition(), others[:8]))
        else:
            wn_note = _downloading("wordnet", self.mgr)

        extra_syn, extra_ant = [], []
        try:
            base = "https://api.datamuse.com/words?max=16&"
            extra_syn = [d["word"] for d in _get_json(base + "rel_syn=" + urllib.parse.quote(w))]
            extra_ant = [d["word"] for d in _get_json(base + "rel_ant=" + urllib.parse.quote(w))]
        except Exception as e:
            log.info("datamuse failed: %s", e)

        shown = {x.lower() for _, _, ws in senses for x in ws}
        extra_syn = [x for x in extra_syn if x.lower() not in shown][:12]
        for a in extra_ant:
            if a not in antonyms:
                antonyms.append(a)

        if not (senses or extra_syn or antonyms):
            return wn_note
        parts = [wn_note]
        for pos, gloss, ws in senses[:6]:
            parts.append(f"<div class='sense'><span class='pos'>{pos}</span> <span class='gloss'>{html.escape(gloss)}</span>"
                         f"<div class='words'>{'、'.join(_word_link(x) for x in ws)}</div></div>")
        if extra_syn:
            parts.append(f"<div class='row'><span class='lbl'>近义</span>{'、'.join(_word_link(x) for x in extra_syn)}</div>")
        if antonyms:
            parts.append(f"<div class='row'><span class='lbl ant'>反义</span>{'、'.join(_word_link(x) for x in antonyms[:12])}</div>")
        parts.append("<div class='src'>来源：WordNet、Datamuse</div>")
        return "".join(parts)


# ---------------------------------------------------------------- wikipedia
class Wikipedia:
    def _summary(self, lang, title):
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title.replace(' ', '_'), safe='')}"
        headers = {"Accept-Language": "zh-cn"} if lang == "zh" else {}
        try:
            data = _get_json(url, headers)
        except Exception as e:
            log.info("wikipedia %s/%s: %s", lang, title, e)
            return None
        if data.get("type") in ("disambiguation", "no-extract") or not data.get("extract"):
            return None
        return data

    def _zh_title(self, en_title):
        url = ("https://en.wikipedia.org/w/api.php?action=query&format=json&prop=langlinks&lllang=zh&redirects=1&titles="
               + urllib.parse.quote(en_title))
        try:
            pages = _get_json(url)["query"]["pages"]
            for p in pages.values():
                for ll in p.get("langlinks", []):
                    return ll.get("*")
        except Exception as e:
            log.info("wikipedia langlinks %s: %s", en_title, e)
        return None

    def __call__(self, q, word):
        if CJK.search(q):
            zh, en = self._summary("zh", q), None
        else:
            en = self._summary("en", word)
            zh_title = self._zh_title(en["title"]) if en else None
            zh = self._summary("zh", zh_title) if zh_title else None
        if not (zh or en):
            return ""
        parts = []
        lead = zh or en
        thumb = (lead.get("thumbnail") or {}).get("source")
        if thumb:
            parts.append(f"<img class='thumb' src='{html.escape(thumb)}'>")
        for data, cls in ((zh, "zh"), (en, "en")):
            if not data:
                continue
            link = data.get("content_urls", {}).get("desktop", {}).get("page", "")
            parts.append(f"<div class='wiki {cls}'><div class='title'><a href='{html.escape(link)}'>"
                         f"{html.escape(data['title'])}</a></div><div class='extract'>{html.escape(data['extract'])}</div></div>")
        parts.append("<div class='src' style='clear:both'>来源：维基百科（CC BY-SA）</div>")
        return "".join(parts)


# ---------------------------------------------------------------- service
class SectionService(QObject):
    ready = Signal(str, str, str)  # query, source id, html

    def __init__(self, cfg, mgr):
        super().__init__()
        self.cfg = cfg
        self.providers = {"examples": Examples(mgr), "thesaurus": Thesaurus(mgr), "wiki": Wikipedia()}
        self.providers["thesaurus"].warm_up()
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="section")
        self.cache = OrderedDict()

    def wanted(self, q):
        """Built-in sections to fetch for a query (none for whole sentences)."""
        if is_sentence(q):
            return []
        return [s["id"] for s in self.cfg.data["sources"]
                if s["id"] in self.providers and s.get("enabled", True)]

    def cached(self, sid, word):
        return self.cache.get((sid, word.casefold()))

    def fetch(self, q, word, sids):
        for sid in sids:
            hit = self.cached(sid, word)
            if hit is not None:
                self.ready.emit(q, sid, hit)
            else:
                self.pool.submit(self._run, q, word, sid)

    def _run(self, q, word, sid):
        try:
            out = self.providers[sid](q, word)
        except Exception:
            log.exception("section %s failed for %r", sid, word)
            out = ""
        if "class='dim'" not in out:  # don't cache "downloading…" placeholders
            self.cache[(sid, word.casefold())] = out
            while len(self.cache) > 300:
                self.cache.popitem(last=False)
        self.ready.emit(q, sid, out)
