"""Offline datasets downloaded on first use: Tatoeba English–Chinese sentence pairs and WordNet.

Both are free (Tatoeba: CC-BY 2.0 FR; WordNet: Princeton WordNet license). Nothing is bundled
with the app; files land in DATA_DIR/data.
"""
import bz2
import csv
import io
import logging
import os
import sqlite3
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

from .config import DATA_DIR

log = logging.getLogger(__name__)

DATA = DATA_DIR / "data"
EXAMPLES_DB = DATA / "examples.sqlite"
NLTK_DIR = DATA / "nltk_data"
WORDNET_ZIP = NLTK_DIR / "corpora" / "wordnet.zip"

TATOEBA = "https://downloads.tatoeba.org/exports/per_language"
WORDNET_URL = "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip"
USER_AGENT = "InstantDic/0.1 (desktop dictionary)"

DATASETS = {
    "examples": {"label": "Tatoeba 中英例句", "size": "约 26 MB"},
    "wordnet": {"label": "WordNet 英文同义词库", "size": "约 11 MB"},
}


def is_ready(name):
    return {"examples": EXAMPLES_DB, "wordnet": WORDNET_ZIP}[name].exists()


def _download(url, progress, label):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            buf.write(chunk)
            if total:
                progress(f"下载 {label} {buf.tell() * 100 // total}%")
    return buf.getvalue()


def _tsv(data):
    # Stream-decompress: the English file is ~150 MB of text once unpacked.
    text = io.TextIOWrapper(bz2.BZ2File(io.BytesIO(data)), encoding="utf-8", errors="replace", newline="")
    return csv.reader(text, delimiter="\t", quoting=csv.QUOTE_NONE)


def build_examples(progress):
    links = _download(f"{TATOEBA}/eng/eng-cmn_links.tsv.bz2", progress, "对照表")
    pairs = [(int(r[0]), int(r[1])) for r in _tsv(links) if len(r) >= 2]
    cmn = {int(r[0]): r[2] for r in _tsv(_download(f"{TATOEBA}/cmn/cmn_sentences.tsv.bz2", progress, "中文句子"))
           if len(r) >= 3}
    wanted = {e for e, _ in pairs}
    eng = {}
    for r in _tsv(_download(f"{TATOEBA}/eng/eng_sentences.tsv.bz2", progress, "英文句子")):
        if len(r) >= 3 and int(r[0]) in wanted:
            eng[int(r[0])] = r[2]
    progress("建立例句索引")
    from opencc import OpenCC  # Tatoeba mixes traditional and simplified Chinese
    t2s = OpenCC("t2s")
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = EXAMPLES_DB.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    # porter stemming: "run" also matches "runs"/"running"
    con.execute("CREATE VIRTUAL TABLE ex USING fts5(eng, cmn, tokenize='porter unicode61')")
    seen = set()
    rows = []
    for e, c in pairs:
        if e in eng and c in cmn and e not in seen:
            seen.add(e)
            rows.append((eng[e], t2s.convert(cmn[c])))
    con.executemany("INSERT INTO ex VALUES (?,?)", rows)
    con.commit()
    con.close()
    os.replace(tmp, EXAMPLES_DB)
    log.info("examples db built: %d pairs", len(rows))


def build_wordnet(progress):
    data = _download(WORDNET_URL, progress, "WordNet")
    WORDNET_ZIP.parent.mkdir(parents=True, exist_ok=True)
    tmp = WORDNET_ZIP.with_suffix(".part")
    tmp.write_bytes(data)
    os.replace(tmp, WORDNET_ZIP)


class DatasetManager(QObject):
    progress = Signal(str, str)        # dataset name, message
    finished = Signal(str, str)        # dataset name, error ("" on success)

    def __init__(self):
        super().__init__()
        self.running = set()

    def ensure(self, name):
        """Start downloading a dataset in the background if it is missing."""
        if is_ready(name) or name in self.running:
            return
        self.running.add(name)
        builder = {"examples": build_examples, "wordnet": build_wordnet}[name]

        def work():
            err = ""
            try:
                builder(lambda msg: self.progress.emit(name, msg))
            except Exception as e:
                log.exception("dataset %s failed", name)
                err = str(e) or e.__class__.__name__
            self.running.discard(name)
            self.finished.emit(name, err)

        threading.Thread(target=work, daemon=True, name=f"dataset-{name}").start()
