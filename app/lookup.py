"""Lookup engine: runs a query against every enabled source in the user's order."""
import logging
import re

from .dictionaries import INDEX_DIR, MdxDictionary, index_is_current

log = logging.getLogger(__name__)

# Inflection fallbacks tried only when the exact word is missing from every dictionary.
_SUFFIX_RULES = [
    ("ies", "y"), ("ied", "y"), ("ier", "y"), ("iest", "y"),
    ("ves", "f"), ("ves", "fe"),
    ("sses", "ss"), ("xes", "x"), ("ches", "ch"), ("shes", "sh"), ("es", "e"), ("es", ""), ("s", ""),
    ("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"), ("d", ""),
    ("er", ""), ("er", "e"), ("est", ""), ("est", "e"), ("ly", ""), ("'s", ""),
]


def _rule_lemmas(w):
    out = []
    for suf, rep in _SUFFIX_RULES:
        if w.endswith(suf) and len(w) - len(suf) >= 2:
            stem = w[: -len(suf)] + rep
            out.append(stem)
            # doubled consonant: stopped -> stop, bigger -> big
            if suf in ("ing", "ed", "er", "est") and len(stem) >= 3 and stem[-1] == stem[-2]:
                out.append(stem[:-1])
    return out


def _lemmas(w):
    """Dictionary lemmas (handles irregulars: went->go, mice->mouse), then suffix rules."""
    out = []
    try:
        from lemminflect import getAllLemmas
        for forms in getAllLemmas(w).values():
            out.extend(forms)
    except Exception:
        log.exception("lemminflect failed for %r", w)
    return out + _rule_lemmas(w)


def lemma_candidates(word):
    w = " ".join(word.strip().lower().split())
    if not re.fullmatch(r"[a-z'\- ]+", w):
        return []
    tokens = w.split()
    if len(tokens) == 1:
        out = _lemmas(w)
    elif len(tokens) <= 4:
        # phrases: "looked up" -> "look up", "ran out of" -> "run out of"
        out = []
        for i, t in enumerate(tokens):
            for lem in _lemmas(t)[:2]:
                out.append(" ".join(tokens[:i] + [lem] + tokens[i + 1:]))
    else:
        return []
    seen = {w}
    return [c for c in out if not (c in seen or seen.add(c))]


class LookupEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.dicts = {}
        self.reload()

    def reload(self):
        for d in self.dicts.values():
            d.close()
        self.dicts = {}
        for src in self.cfg.data["sources"]:
            if src.get("type") != "mdx":
                continue
            db = INDEX_DIR / f"{src['id']}.sqlite"
            if not db.exists():
                continue
            try:
                self.dicts[src["id"]] = MdxDictionary(src)
            except Exception:
                log.exception("failed to open dictionary %s", src.get("path"))

    def close(self, source_id):
        d = self.dicts.pop(source_id, None)
        if d is not None:
            d.close()

    def stale_sources(self):
        """Sources whose index is missing or older than the dictionary files."""
        return [s for s in self.cfg.data["sources"] if s.get("type") == "mdx"
                and not index_is_current(s["path"], INDEX_DIR / f"{s['id']}.sqlite")]

    def enabled_dicts(self):
        for src in self.cfg.data["sources"]:
            if src.get("enabled", True) and src["id"] in self.dicts:
                yield src, self.dicts[src["id"]]

    def lookup(self, query):
        """-> (sections, resolved_word). sections: [(source, [html, ...])] in display order.
        Empty sections means no dictionary knows the word (the AI fallback trigger)."""
        q = query.strip()
        hits = [(src, d.lookup(q)) for src, d in self.enabled_dicts()]
        hits = [(s, h) for s, h in hits if h]
        if hits:
            return hits, q
        for cand in lemma_candidates(q):
            hits = [(src, d.lookup(cand)) for src, d in self.enabled_dicts()]
            hits = [(s, h) for s, h in hits if h]
            if hits:
                return hits, cand
        return [], q

    def suggest(self, prefix, limit=12):
        seen, out = set(), []
        for _src, d in self.enabled_dicts():
            for k in d.suggest(prefix, limit):
                if k.casefold() not in seen:
                    seen.add(k.casefold())
                    out.append(k)
        out.sort(key=lambda k: (len(k), k.casefold() != k, k.casefold()))
        return out[:limit]

    def dictionary(self, source_id):
        return self.dicts.get(source_id)
