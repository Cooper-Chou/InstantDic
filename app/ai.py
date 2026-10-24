"""AI translation fallback over any OpenAI-compatible streaming chat API (DeepSeek, Qwen, OpenAI, …).

The only AI call in the app. It runs only when no dictionary has the word, or when the
user clicks the AI button. Results are cached so a repeat lookup costs no tokens.
"""
import json
import logging
import re
import sqlite3
import time

import keyring
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import ai_providers
from .config import DATA_DIR

log = logging.getLogger(__name__)

KEYRING_SERVICE = "InstantDic"
KEYRING_USER = "ai-api-key"
TIMEOUT_MS = 30000

WORD_PROMPT = """你是一部简明的英汉双向词典。用户给出一个单词或短语，请按下面格式用 Markdown 输出，不要多余的开场白：
**词条** /音标/（英文词条才给音标）
- 词性. 中文释义（常用义项在前，最多 4 条）
**例句**
- 英文例句 —— 中文翻译（2 句）
如果输入是中文，就给出对应的英文表达（最多 4 个，附简短用法区别）和例句。
如果输入有拼写错误，先在第一行写「你可能想查：xxx」再解释正确的词。"""

SENTENCE_PROMPT = """你是专业翻译。用户输入英文时翻译成自然流畅的简体中文；输入中文时翻译成地道的英文；其他语言翻译成简体中文。
只输出译文，不要解释、不要加引号。"""


def is_sentence(text):
    t = text.strip()
    if re.search(r"[一-鿿]", t):
        return len(t) > 6 or bool(re.search(r"[，。！？,.!?]", t))
    return len(t.split()) > 4 or bool(re.search(r"[.!?;]\s*$", t) and len(t.split()) > 1)


def get_api_key():
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
    except Exception:
        log.exception("keyring read failed")
        return ""


def set_api_key(key):
    if key:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)
    else:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
        except keyring.errors.PasswordDeleteError:
            pass


class _Cache:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DATA_DIR / "ai_cache.sqlite")
        self.db.execute("CREATE TABLE IF NOT EXISTS ai(q TEXT, mode TEXT, model TEXT, text TEXT, ts REAL, "
                        "PRIMARY KEY(q, mode, model))")

    @staticmethod
    def _key(q):
        return " ".join(q.split())

    def get(self, q, mode, model):
        row = self.db.execute("SELECT text FROM ai WHERE q=? AND mode=? AND model=?",
                              (self._key(q), mode, model)).fetchone()
        return row[0] if row else None

    def put(self, q, mode, model, text):
        self.db.execute("INSERT OR REPLACE INTO ai VALUES (?,?,?,?,?)", (self._key(q), mode, model, text, time.time()))
        self.db.commit()


class AiService(QObject):
    # request id, accumulated text, state ("thinking" / "streaming" / "done" / "error"), error message
    update = Signal(int, str, str, str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.net = QNetworkAccessManager(self)
        self.cache = _Cache()
        self._next_id = 0
        self._active = {}  # id -> dict(reply, buf, text, q, mode, model)

    # ---------- settings ----------
    @property
    def ai_cfg(self):
        return self.cfg.data["ai"]

    def provider(self):
        return self.ai_cfg.get("provider") or "deepseek"

    def base_url(self):
        return (self.ai_cfg.get("base_url") or ai_providers.base_url(self.provider())).rstrip("/")

    def model(self):
        return self.ai_cfg.get("model") or ""

    def configured(self):
        return bool(get_api_key())

    def cached(self, q):
        mode = "sentence" if is_sentence(q) else "word"
        return self.cache.get(q, mode, self.model()) if self.model() else None

    # ---------- translation ----------
    def translate(self, q):
        """Start a streamed translation. Returns a request id; progress arrives via `update`."""
        self._next_id += 1
        rid = self._next_id
        key = get_api_key()
        if not key:
            QTimer.singleShot(0, lambda: self.update.emit(rid, "", "error", "尚未设置 AI 翻译的 API Key"))
            return rid
        if not self.model():
            # First use: pick the provider's cheap/fast model from the account's model list, then start.
            self.list_models(lambda models, err: self._after_autopick(rid, q, models, err))
            return rid
        self._start(rid, q, key)
        return rid

    def _after_autopick(self, rid, q, models, err):
        if err or not models:
            self.update.emit(rid, "", "error", err or "无法获取模型列表，请在设置中手动填写模型名")
            return
        pick = ai_providers.pick_model(self.provider(), models)
        if not pick:
            self.update.emit(rid, "", "error", "没有找到可用的对话模型，请在设置中手动填写模型名")
            return
        log.info("auto-selected model %s from %s", pick, models)
        self.ai_cfg["model"] = pick
        self.cfg.save()
        self._start(rid, q, get_api_key())

    def _start(self, rid, q, key):
        mode = "sentence" if is_sentence(q) else "word"
        model = self.model()
        hit = self.cache.get(q, mode, model)
        if hit is not None:
            QTimer.singleShot(0, lambda: self.update.emit(rid, hit, "done", ""))
            return
        body = {
            "model": model,
            "stream": True,
            "temperature": 0.3,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": SENTENCE_PROMPT if mode == "sentence" else WORD_PROMPT},
                {"role": "user", "content": q},
            ],
        }
        req = self._request("/chat/completions", key)
        req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        req.setRawHeader(b"Accept", b"text/event-stream")
        reply = self.net.post(req, json.dumps(body).encode("utf-8"))
        self._active[rid] = {"reply": reply, "buf": b"", "text": "", "q": q, "mode": mode, "model": model,
                             "t0": time.perf_counter(), "first": None}
        reply.readyRead.connect(lambda: self._on_data(rid))
        reply.finished.connect(lambda: self._on_finished(rid))
        self.update.emit(rid, "", "thinking", "")

    def _request(self, path, key):
        req = QNetworkRequest(QUrl(self.base_url() + path))
        req.setRawHeader(b"Authorization", f"Bearer {key}".encode())
        req.setTransferTimeout(TIMEOUT_MS)
        return req

    def cancel(self, rid):
        st = self._active.pop(rid, None)
        if st:
            st["reply"].abort()
            st["reply"].deleteLater()

    def cancel_all(self):
        for rid in list(self._active):
            self.cancel(rid)

    def _on_data(self, rid):
        st = self._active.get(rid)
        if not st:
            return
        st["buf"] += bytes(st["reply"].readAll())
        *lines, st["buf"] = st["buf"].split(b"\n")
        changed = False
        for line in lines:
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                continue
            try:
                delta = json.loads(payload)["choices"][0].get("delta", {})
            except (ValueError, KeyError, IndexError):
                continue
            piece = delta.get("content") or ""
            if piece:
                if st["first"] is None:
                    st["first"] = time.perf_counter()
                st["text"] += piece
                changed = True
        if changed:
            self.update.emit(rid, st["text"], "streaming", "")

    def _on_finished(self, rid):
        self._on_data(rid)
        st = self._active.pop(rid, None)
        if not st:
            return
        reply = st["reply"]
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        err = ""
        if reply.error() != QNetworkReply.NoError or (status and status >= 400):
            err = self._error_message(status, reply, st["buf"])
        reply.deleteLater()
        if err:
            log.warning("AI request failed: %s", err)
            self.update.emit(rid, st["text"], "error", err)
            return
        text = st["text"].strip()
        first = (st["first"] - st["t0"]) * 1000 if st["first"] else -1
        log.info("AI %s done: first token %.0f ms, total %.0f ms, %d chars", st["mode"], first,
                 (time.perf_counter() - st["t0"]) * 1000, len(text))
        if text:
            self.cache.put(st["q"], st["mode"], st["model"], text)
        self.update.emit(rid, text, "done", "" if text else "AI 没有返回内容")

    @staticmethod
    def _error_message(status, reply, body):
        detail = ""
        try:
            detail = json.loads(body.decode("utf-8", "ignore") or "{}").get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            pass
        known = {401: "API Key 无效，请在设置中检查（也可能是选错了服务商）", 402: "账户余额不足", 403: "没有权限使用该模型或接口", 429: "请求太频繁，请稍后再试",
                 400: "请求格式错误（模型名可能不对）", 404: "接口地址或模型名不存在"}
        if status in known:
            return known[status] + (f"（{detail}）" if detail else "")
        if reply.error() == QNetworkReply.OperationCanceledError:
            return "请求超时"
        return f"网络错误：{reply.errorString()}" + (f"（{detail}）" if detail else "")

    # ---------- model list ----------
    def list_models(self, callback, key=None):
        """callback(models: list[str], error: str)"""
        key = key or get_api_key()
        if not key:
            callback([], "尚未设置 API Key")
            return
        reply = self.net.get(self._request("/models", key))

        def done():
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            body = bytes(reply.readAll())
            if reply.error() != QNetworkReply.NoError or (status and status >= 400):
                callback([], self._error_message(status, reply, body))
            else:
                try:
                    callback(sorted(m["id"] for m in json.loads(body)["data"]), "")
                except (ValueError, KeyError, TypeError):
                    callback([], "模型列表格式无法识别")
            reply.deleteLater()

        reply.finished.connect(done)
