"""Imported MDX dictionaries: per-dictionary SQLite index + runtime lookup."""
import bisect
import hashlib
import json
import logging
import os
import re
import sqlite3
from pathlib import Path

from .config import DATA_DIR
from .i18n import tr
from .mdict import MDict

log = logging.getLogger(__name__)

INDEX_DIR = DATA_DIR / "index"
INDEX_VERSION = 2  # 2: entries.link flags redirect (@@@LINK=) entries
MAX_LINK_DEPTH = 5
_HOMOGRAPH_ID = re.compile(r"_\d+$")  # packager ids such as see_1 / see_2


def source_id_for(mdx_path):
    return "mdx-" + hashlib.sha1(os.path.normcase(os.path.abspath(mdx_path)).encode("utf-8")).hexdigest()[:10]


def norm_key(s):
    return " ".join(s.casefold().split())


def norm_res(path):
    p = path.replace("/", "\\").lower()
    return p if p.startswith("\\") else "\\" + p


def mdd_volumes(mdx_path):
    """name.mdd, name.1.mdd, name.2.mdd ... (empty placeholder files are skipped)."""
    base = str(mdx_path)[:-4]
    vols = [base + ".mdd"] + [f"{base}.{i}.mdd" for i in range(1, 30)]
    return [v for v in vols if os.path.isfile(v) and os.path.getsize(v) > 1024]


def _file_sig(paths):
    return [[os.path.normcase(os.path.abspath(p)), os.path.getsize(p), int(os.path.getmtime(p))] for p in paths]


def build_index(mdx_path, db_path, progress=lambda msg: None):
    """Parse key sections of the .mdx and all .mdd volumes into a fresh SQLite file.
    Returns (title, tmp_path); the caller swaps tmp_path into db_path with install_index()
    once the old index is closed (Windows can't replace an open file)."""
    mdx_path = str(mdx_path)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    con.executescript("""
        CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE entries(key TEXT, norm TEXT, start INTEGER, end INTEGER, link INTEGER);
        CREATE TABLE layout(vol INTEGER, i INTEGER, comp_off INTEGER, comp INTEGER, d_off INTEGER, d INTEGER);
        CREATE TABLE resources(norm TEXT, vol INTEGER, start INTEGER, end INTEGER);
    """)
    files = [mdx_path] + mdd_volumes(mdx_path)
    for vol, path in enumerate(files):
        is_mdd = vol > 0
        progress(tr("读取 {name}", name=os.path.basename(path)))
        m = MDict(path, is_mdd=is_mdd)
        try:
            keys = m.read_keys()
            offsets = sorted({o for _, o in keys})
            offsets.append(m.total_decomp)
            link_offsets = set()
            if not is_mdd:
                # Flag redirect records once here, so suggestions can skip them with a plain query.
                progress(tr("建立索引"))
                marker = "@@@LINK=".encode(m.encoding)
                for o, nxt in zip(offsets, offsets[1:]):
                    if m.read_record(o, min(nxt, o + len(marker) + 8)).lstrip().startswith(marker):
                        link_offsets.add(o)
        finally:
            m.close()
        if vol == 0:
            header = m.header

        def end_of(o):
            return offsets[bisect.bisect_right(offsets, o)]

        if is_mdd:
            con.executemany("INSERT INTO resources VALUES (?,?,?,?)",
                            ((norm_res(k), vol, o, end_of(o)) for k, o in keys))
        else:
            con.executemany("INSERT INTO entries VALUES (?,?,?,?,?)",
                            ((k, norm_key(k), o, end_of(o), int(o in link_offsets)) for k, o in keys))
        con.executemany("INSERT INTO layout VALUES (?,?,?,?,?,?)",
                        ((vol, i, *b) for i, b in enumerate(m.record_layout)))
    progress(tr("建立索引"))
    con.executescript("""
        CREATE INDEX entries_norm ON entries(norm);
        CREATE INDEX resources_norm ON resources(norm);
    """)
    meta = {
        "index_version": INDEX_VERSION,
        "files": json.dumps(_file_sig(files)),
        "title": header.get("Title", ""),
        "header": json.dumps(header, ensure_ascii=False),
    }
    con.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    con.commit()
    con.close()
    return header.get("Title", ""), tmp


def install_index(tmp, db_path):
    os.replace(tmp, db_path)


def index_is_current(mdx_path, db_path):
    if not Path(db_path).exists():
        return False
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        meta = dict(con.execute("SELECT k, v FROM meta"))
        con.close()
        files = [mdx_path] + mdd_volumes(mdx_path)
        return (int(meta.get("index_version", 0)) == INDEX_VERSION
                and json.loads(meta["files"]) == _file_sig(files))
    except Exception:
        log.exception("index check failed for %s", mdx_path)
        return False


class MdxDictionary:
    def __init__(self, source):
        self.id = source["id"]
        self.name = source.get("name") or Path(source["path"]).stem
        self.mdx_path = source["path"]
        self.folder = Path(self.mdx_path).parent
        self.db = sqlite3.connect(INDEX_DIR / f"{self.id}.sqlite", check_same_thread=False)
        files = json.loads(self.db.execute("SELECT v FROM meta WHERE k='files'").fetchone()[0])
        self._paths = [f[0] for f in files]
        self._vols = {}
        self._links = {}  # key -> redirect target (None for real entries)
        # Indexes built before INDEX_VERSION 2 have no link column; they keep working (unfiltered)
        # until the background rebuild replaces them.
        self._has_link = any(c[1] == "link" for c in self.db.execute("PRAGMA table_info(entries)"))

    def close(self):
        for m in self._vols.values():
            m.close()
        self.db.close()

    def _vol(self, vol):
        m = self._vols.get(vol)
        if m is None:
            m = MDict(self._paths[vol], is_mdd=vol > 0)
            rows = self.db.execute("SELECT comp_off, comp, d_off, d FROM layout WHERE vol=? ORDER BY i", (vol,))
            m.set_record_layout([tuple(r) for r in rows])
            self._vols[vol] = m
        return m

    # ---------- entries ----------
    def has(self, word):
        return self.db.execute("SELECT 1 FROM entries WHERE norm=? LIMIT 1", (norm_key(word),)).fetchone() is not None

    def lookup(self, word, _depth=0):
        """All entry HTML fragments for a word, following @@@LINK= redirects."""
        rows = self.db.execute("SELECT key, start, end FROM entries WHERE norm=? ORDER BY rowid",
                               (norm_key(word),)).fetchall()
        out, seen = [], set()
        m = self._vol(0)
        for _key, start, end in rows:
            if (start, end) in seen:
                continue
            seen.add((start, end))
            text = m.decode_text(m.read_record(start, end)).strip()
            if text.startswith("@@@LINK="):
                target = text[len("@@@LINK="):].strip()
                if _depth < MAX_LINK_DEPTH and norm_key(target) != norm_key(word):
                    out.extend(self.lookup(target, _depth + 1))
                continue
            out.append(text)
        return out

    def _link_target(self, key):
        """Target of an @@@LINK redirect entry, or None for a real entry (cached)."""
        if key in self._links:
            return self._links[key]
        row = self.db.execute("SELECT start, end FROM entries WHERE key=? LIMIT 1", (key,)).fetchone()
        target = None
        if row:
            m = self._vol(0)
            head = m.decode_text(m.read_record(row[0], min(row[1], row[0] + 512))).strip()
            if head.startswith("@@@LINK="):
                target = head[len("@@@LINK="):].splitlines()[0].strip() or None
        if len(self._links) > 20000:
            self._links.clear()
        self._links[key] = target
        return target

    def suggest(self, prefix, limit=30):
        """Real headwords starting with prefix. Redirect entries (homograph ids like "see_1",
        hyphen aliases like "see-in", inflections like "sees") are lookup aliases, not words to
        offer; if the typed text itself is such an alias, its target is offered first instead."""
        p = norm_key(prefix)
        if not p:
            return []
        rows = self.db.execute(
            "SELECT DISTINCT key FROM entries WHERE norm >= ? AND norm < ? "
            + ("AND link = 0 " if self._has_link else "") +
            "AND substr(key,1,1) NOT IN ('_','@') ORDER BY length(norm), norm LIMIT ?",
            (p, p + "\U0010ffff", limit * 2))
        out = [k for (k,) in rows if not _HOMOGRAPH_ID.search(k)][:limit]
        exact = self.db.execute("SELECT key FROM entries WHERE norm=? LIMIT 1", (p,)).fetchone()
        target = self._link_target(exact[0]) if exact else None
        if target and target not in out and not _HOMOGRAPH_ID.search(target):
            out.insert(0, target)
        return out[:limit]

    # ---------- resources ----------
    def resource(self, path):
        """Bytes for a resource referenced by entry HTML: loose file next to the .mdx first, then .mdd."""
        rel = path.lstrip("/\\").replace("\\", "/")
        if rel and ".." not in rel.split("/"):
            loose = self.folder / rel
            if loose.is_file():
                return loose.read_bytes()
        row = self.db.execute("SELECT vol, start, end FROM resources WHERE norm=? LIMIT 1",
                              (norm_res(rel),)).fetchone()
        if row is None:
            return None
        vol, start, end = row
        return self._vol(vol).read_record(start, end)
