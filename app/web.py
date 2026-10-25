"""mdict:// scheme: result page, per-dictionary entry documents and .mdd resources.

  mdict://app/result?q=word        result page (one section per dictionary, in user order)
  mdict://<source-id>/entry?k=word  one dictionary's entry, rendered in its own iframe so
                                    each dictionary's CSS/JS stays isolated
  mdict://<source-id>/<path>        resource (css/js/img/audio) from the folder or .mdd
"""
import html
import json
import logging
import mimetypes
from urllib.parse import quote

from PySide6.QtCore import QBuffer, QByteArray, QUrl, QUrlQuery, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineUrlRequestJob, QWebEngineUrlScheme, \
    QWebEngineUrlSchemeHandler

from . import ai_providers
from .audio import SpeexTranscoder
from .config import section_name
from .i18n import tr
from .theme import THEMES

log = logging.getLogger(__name__)

SCHEME = b"mdict"
_EXTRA_MIME = {".js": "application/javascript", ".css": "text/css",
               ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".svg": "image/svg+xml"}


def register_scheme():
    """Must run before QApplication is created."""
    s = QWebEngineUrlScheme(SCHEME)
    s.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    s.setFlags(QWebEngineUrlScheme.Flag.SecureScheme | QWebEngineUrlScheme.Flag.LocalAccessAllowed
               | QWebEngineUrlScheme.Flag.CorsEnabled | QWebEngineUrlScheme.Flag.ContentSecurityPolicyIgnored
               | QWebEngineUrlScheme.Flag.FetchApiAllowed)
    QWebEngineUrlScheme.registerScheme(s)


def result_url(query, force_ai=False):
    return QUrl(f"mdict://app/result?q={quote(query, safe='')}" + ("&ai=1" if force_ai else ""))


# Injected first into every entry document: some dictionary scripts call scrollIntoView() on
# load, which would scroll the whole result page away from the top.
ENTRY_PRELUDE = ("<script>(function(){var t=Date.now(),o=Element.prototype.scrollIntoView;"
                 "Element.prototype.scrollIntoView=function(){if(Date.now()-t>1500)return o.apply(this,arguments);};"
                 "})();</script>")

# Injected into every entry document: reports height to the parent, routes dictionary links.
ENTRY_SCRIPT = r"""<script>(function(){
var FID=%s;
// Measure the content wrapper, not documentElement.scrollHeight: the latter is never smaller than the
// iframe itself, so growing the iframe to fit it made it grow forever.
var last=-1;
function send(){var w=document.getElementById('__ie_entry'); if(!w)return;
 var cs=getComputedStyle(document.body);
 var h=Math.ceil(w.getBoundingClientRect().height+parseFloat(cs.marginTop)+parseFloat(cs.marginBottom));
 if(Math.abs(h-last)<2)return; last=h;
 parent.postMessage({t:'h',id:FID,h:h},'*');}
document.addEventListener('DOMContentLoaded',function(){
 var w=document.getElementById('__ie_entry'); if(w)new ResizeObserver(send).observe(w); send();});
window.addEventListener('load',send);
document.addEventListener('click',function(e){
 var a=e.target.closest&&e.target.closest('a'); if(!a)return;
 var href=a.getAttribute('href')||'';
 if(href.indexOf('sound://')===0){e.preventDefault();e.stopPropagation();
  new Audio('/'+href.slice(8).replace(/\\/g,'/').replace(/^\/+/,'')).play().catch(function(err){
   parent.postMessage({t:'audioerr',src:href},'*');});}
 else if(href.indexOf('entry://')===0){e.preventDefault();e.stopPropagation();
  var t=decodeURIComponent(href.slice(8)),hash='',i=t.indexOf('#');
  if(i>=0){hash=t.slice(i+1);t=t.slice(0,i);}
  if(!t&&hash){var el=document.getElementById(hash)||document.getElementsByName(hash)[0];
   if(el)parent.postMessage({t:'scroll',id:FID,y:el.getBoundingClientRect().top+window.scrollY},'*');}
  else if(t&&t[0]!=='@')parent.postMessage({t:'lookup',q:t},'*');}
 else if(/^https?:/i.test(href)){e.preventDefault();parent.postMessage({t:'open',url:href},'*');}
},true);
})();</script>"""

DARK_ENTRY_CSS = ("<style>html{filter:invert(.88) hue-rotate(180deg);background:#fff}"
                  "img,video,picture{filter:invert(1) hue-rotate(180deg)}</style>")

PAGE_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><style>
:root {{ color-scheme:{scheme}; --bg:{bg}; --panel:{panel}; --text:{text}; --muted:{muted}; --border:{border}; --accent:{accent}; --hover:{hover}; }}
html,body {{ margin:0; background:var(--bg); color:var(--text);
  font-family:"Segoe UI","Microsoft YaHei UI",sans-serif; font-size:14px; }}
.sec {{ border-bottom:1px solid var(--border); }}
.sec-head {{ display:flex; align-items:center; gap:6px; padding:6px 12px; background:var(--panel);
  color:var(--muted); font-size:12px; cursor:pointer; user-select:none; position:sticky; top:0; z-index:2; }}
.sec-head:hover {{ color:var(--text); }}
.sec-head .arrow {{ transition:transform .15s; display:inline-block; }}
.sec.collapsed .arrow {{ transform:rotate(-90deg); }}
.sec.collapsed > :not(.sec-head) {{ display:none; }}
iframe {{ display:block; width:100%; border:0; height:60px; background:var(--bg); }}
.msg {{ padding:24px 16px; color:var(--muted); line-height:1.7; }}
.msg b {{ color:var(--text); }}
.note {{ padding:4px 12px; color:var(--muted); font-size:12px; }}
.ai-body {{ padding:10px 16px 14px; line-height:1.65; font-size:14.5px; user-select:text; }}
.ai-body p {{ margin:0 0 4px; }} .ai-body ul {{ margin:2px 0 6px; padding-left:20px; }}
.ai-body h4 {{ margin:8px 0 4px; font-size:14.5px; }} .ai-body .gap {{ height:6px; }}
.ai-body code {{ background:var(--panel); padding:0 4px; border-radius:3px; }}
.ai-body .muted, .ai-tag {{ color:var(--muted); }} .ai-tag {{ font-size:11px; margin-left:auto; }}
.ai-body .err {{ color:#e5484d; margin-top:6px; }}
.cursor {{ animation:blink 1s steps(1) infinite; color:var(--accent); }}
@keyframes blink {{ 50% {{ opacity:0; }} }}
.ai-btn {{ display:inline-block; margin:10px 12px 14px; padding:4px 10px; border:1px solid var(--border);
  border-radius:6px; color:var(--muted); text-decoration:none; font-size:12px; }}
.ai-btn:hover {{ color:var(--text); background:var(--hover); }}
.sec-body {{ padding:8px 16px 12px; line-height:1.6; }}
.sec-body a {{ color:var(--accent); text-decoration:none; }} .sec-body a:hover {{ text-decoration:underline; }}
.sec-body .src, .sec-body .dim {{ color:var(--muted); font-size:11.5px; margin-top:6px; }}
.ex {{ margin:0; padding-left:22px; }} .ex li {{ margin:0 0 7px; }}
.ex .en b, .ex .zh b {{ color:var(--accent); }} .ex .zh {{ color:var(--muted); }}
.sense {{ margin:0 0 7px; }} .sense .pos {{ color:var(--accent); font-style:italic; margin-right:2px; }}
.sense .gloss {{ color:var(--muted); font-size:13px; }}
.row {{ margin:6px 0; }} .lbl {{ display:inline-block; font-size:11.5px; padding:0 6px; margin-right:6px;
  border-radius:4px; background:var(--panel); color:var(--muted); }} .lbl.ant {{ color:#e5484d; }}
.wiki {{ margin-bottom:8px; }} .wiki .title {{ font-weight:600; margin-bottom:2px; }}
.wiki.en .extract {{ color:var(--muted); font-size:13px; }}
.thumb {{ float:right; max-width:96px; max-height:96px; margin:2px 0 6px 12px; border-radius:6px; }}
</style></head><body>{body}
<script>
window.addEventListener('message',function(e){{var m=e.data||{{}};
 if(m.t==='h'){{var f=document.getElementById(m.id); if(f)f.style.height=m.h+'px';}}
 else if(m.t==='lookup'){{location.href='mdict://app/result?q='+encodeURIComponent(m.q);}}
 else if(m.t==='open'){{location.href=m.url;}}
 else if(m.t==='scroll'){{var f=document.getElementById(m.id); if(f)window.scrollTo(0,f.offsetTop+m.y-40);}}
 else if(m.t==='audioerr'){{console.log('audio failed '+m.src);}}
}});
document.querySelectorAll('.sec-head').forEach(function(h){{h.addEventListener('click',function(){{
 h.parentElement.classList.toggle('collapsed');}});}});
</script></body></html>"""


# Renders the AI section; the popup pushes streamed text in with aiSet(text, state, error).
AI_SCRIPT = r"""<script>
function esc(s){return s.replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function inl(s){return s.replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/(^|[^*])\*([^*\s][^*]*?)\*/g,'$1<i>$2</i>')
 .replace(/`([^`]+)`/g,'<code>$1</code>');}
function md(src){var out=[],list=false;esc(src).split('\n').forEach(function(l){var m;
 if((m=l.match(/^\s*[-*•]\s+(.*)/))){if(!list){out.push('<ul>');list=true;}out.push('<li>'+inl(m[1])+'</li>');return;}
 if(list){out.push('</ul>');list=false;}
 if((m=l.match(/^#{1,4}\s+(.*)/))){out.push('<h4>'+inl(m[1])+'</h4>');return;}
 if(!l.trim()){out.push('<div class="gap"></div>');return;}
 out.push('<p>'+inl(l)+'</p>');});
 if(list)out.push('</ul>');return out.join('');}
function setSection(id,h){var s=document.getElementById('sec-'+id);if(!s)return;
 if(!h){s.hidden=true;return;} s.querySelector('.sec-body').innerHTML=h; s.hidden=false;}
function aiSet(t,st,err){var b=document.getElementById('ai-body');if(!b)return;
 if(st==='thinking'&&!t){b.innerHTML='<span class="muted">__AI_BUSY__</span>';return;}
 var h=md(t||'');if(st==='streaming')h+='<span class="cursor">▍</span>';
 if(st==='error')h+='<div class="err">'+esc(err||'__AI_ERR__')+'</div>';
 b.innerHTML=h;}
</script>"""


class SchemeHandler(QWebEngineUrlSchemeHandler):
    aiNeeded = Signal(str)  # query whose result page is waiting for an AI translation
    sectionsNeeded = Signal(str, str, list)  # query, resolved word, built-in source ids

    def __init__(self, engine, ai, sections, cfg, theme_name_fn, parent=None):
        super().__init__(parent)
        self.engine, self.ai, self.sections, self.cfg = engine, ai, sections, cfg
        self.theme_name = theme_name_fn  # -> "light" / "dark"
        self.speex = SpeexTranscoder(self)

    def requestStarted(self, job: QWebEngineUrlRequestJob):
        url = job.requestUrl()
        host, path = url.host(), url.path()
        query = QUrlQuery(url)
        try:
            if host == "app":
                if path == "/result":
                    return self._reply(job, "text/html", self.result_page(
                        query.queryItemValue("q", QUrl.FullyDecoded), query.queryItemValue("ai") == "1"))
                if path == "/home":
                    return self._reply(job, "text/html", self.home_page())
            else:
                d = self.engine.dictionary(host)
                if d is None:
                    return job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                if path == "/entry":
                    word = query.queryItemValue("k", QUrl.FullyDecoded)
                    fid = query.queryItemValue("fid", QUrl.FullyDecoded)
                    return self._reply(job, "text/html", self.entry_doc(d, word, fid))
                data = d.resource(QUrl.fromPercentEncoding(path.encode("utf-8")))
                if data is not None and path.lower().endswith(".spx"):
                    return self._reply_speex(job, f"{host}{path}", data)
                if data is not None:
                    return self._reply(job, self._mime(path), data)
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
        except Exception:
            log.exception("scheme request failed: %s", url.toString())
            job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)

    def _reply_speex(self, job, key, data):
        """Chromium can't play Speex: transcode to WAV, then answer the (still pending) request."""
        alive = [True]
        job.destroyed.connect(lambda *_: alive.__setitem__(0, False))

        def done(wav):
            if not alive[0]:
                return
            if wav:
                self._reply(job, "audio/wav", wav)
            else:
                job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)

        self.speex.to_wav(key, data, done)

    @staticmethod
    def _mime(path):
        ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""
        return _EXTRA_MIME.get(ext) or mimetypes.types_map.get(ext) or "application/octet-stream"

    @staticmethod
    def _reply(job, mime, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
            mime += "; charset=utf-8"
        buf = QBuffer(job)
        buf.setData(QByteArray(data))
        job.reply(mime.encode(), buf)

    def _page(self, body):
        return PAGE_TEMPLATE.format(body=body, **THEMES[self.theme_name()])

    def home_page(self):
        if not self.engine.dicts:
            return self._page("<div class='msg'>" + tr("还没有导入词典。<br>右键托盘图标 → <b>设置</b> → <b>导入词典</b>，选择 .mdx 文件。") + "</div>")
        return self._page("<div class='msg'>" + tr("输入单词后回车查询。") + "</div>")

    def result_page(self, q, force_ai=False):
        q = q.strip()
        if not q:
            return self.home_page()
        sections, word = self.engine.lookup(q)
        hits = {src["id"]: src for src, _frags in sections}
        ai_src = next((s for s in self.cfg.data["sources"] if s["id"] == "ai"), None)
        ai_on = bool(ai_src and ai_src.get("enabled", True))
        want_ai = ai_on and (force_ai or not sections)

        builtin = self.sections.wanted(q)
        if not sections and not want_ai and not builtin:
            return self._page("<div class='msg'>" + tr("本地词典中没有找到 <b>{q}</b>。<br>（AI 翻译已在设置中停用。）", q=html.escape(q))
                              + "</div>")
        lookup_word = word if sections else q
        parts = [AI_SCRIPT.replace("__AI_BUSY__", tr("AI 正在翻译…")).replace("__AI_ERR__", tr("出错了"))]
        pending = []
        if not sections:
            parts.append("<div class='note'>" + tr("本地词典中没有找到 {q}", q=html.escape(q)) + "</div>")
        elif word.casefold() != q.casefold():
            parts.append("<div class='note'>" + tr("未找到 {q}，显示 <b>{word}</b> 的结果", q=html.escape(q), word=html.escape(word)) + "</div>")
        # Clicking "用 AI 翻译" puts the AI section first so it's visible without scrolling.
        if want_ai and sections:
            parts.append(self._ai_section(ai_src, q))
        for i, src in enumerate(self.cfg.data["sources"]):
            if src["id"] in hits:
                parts.append(self._dict_section(src, word, f"f{i}"))
            elif src["id"] == "ai" and want_ai and not sections:
                parts.append(self._ai_section(src, q))
            elif src["id"] in builtin:
                parts.append(self._async_section(src, lookup_word, pending))
        if pending:
            self.sectionsNeeded.emit(q, lookup_word, pending)
        if sections and ai_on and not want_ai and self.cfg.data["ai"].get("show_button", True):
            parts.append(f"<a class='ai-btn' href='{result_url(q, True).toString()}'>{tr("用 AI 翻译")}</a>")
        return self._page("".join(parts))

    def _dict_section(self, src, word, fid):
        collapsed = " collapsed" if src.get("collapsed") else ""
        name = html.escape(section_name(src))
        return (f"<div class='sec{collapsed}'><div class='sec-head'><span class='arrow'>▾</span>{name}</div>"
                f"<iframe id='{fid}' src='mdict://{src['id']}/entry?k={quote(word, safe='')}&fid={fid}'></iframe></div>")

    def _async_section(self, src, word, pending):
        """Placeholder filled in later by setSection(); stays hidden if the source has nothing."""
        collapsed = " collapsed" if src.get("collapsed") else ""
        cached = self.sections.cached(src["id"], word)
        hidden = "" if cached else " hidden"
        if cached is None:
            pending.append(src["id"])
        return (f"<div class='sec{collapsed}' id='sec-{src['id']}'{hidden}><div class='sec-head'><span class='arrow'>▾</span>"
                f"{html.escape(section_name(src))}</div><div class='sec-body'>{cached or ''}</div></div>")

    def _ai_section(self, src, q):
        collapsed = " collapsed" if src.get("collapsed") else ""
        model = html.escape(" · ".join(x for x in (ai_providers.label(self.ai.provider()), self.ai.model()) if x))
        head = (f"<div class='sec-head'><span class='arrow'>▾</span>{html.escape(section_name(src))}"
                f"<span class='ai-tag'>{tr('AI 生成，仅供参考')}{(' · ' + model) if model else ''}</span></div>")
        if not self.ai.configured():
            body = ("<div class='ai-body'><span class='muted'>"
                    + tr("尚未设置 AI 翻译的 API Key。<br>右键托盘图标 → <b>设置</b> → <b>AI 翻译</b> 填写后即可使用。") + "</span></div>")
            return f"<div class='sec{collapsed}'>{head}{body}</div>"
        init = ""
        cached = self.ai.cached(q)
        if cached is not None:
            init = f"<script>aiSet({json.dumps(cached)},'done','');</script>"
        else:
            self.aiNeeded.emit(q)
        return (f"<div class='sec{collapsed}'>{head}<div id='ai-body' class='ai-body'>"
                f"<span class='muted'>{tr('AI 正在翻译…')}</span></div></div>{init}")

    def entry_doc(self, d, word, fid):
        frags = d.lookup(word)
        dark = DARK_ENTRY_CSS if self.theme_name() == "dark" else ""
        body = "<hr style='border:0;border-top:1px dashed #ccc'>".join(frags)
        return (f"<meta charset='utf-8'>{ENTRY_PRELUDE}<style>body{{margin:8px 12px;}}</style>{dark}"
                f"<div id='__ie_entry' style='display:flow-root'>{body}</div>{ENTRY_SCRIPT % json.dumps(fid)}")


class ResultPage(QWebEnginePage):
    """Opens web links in the system browser instead of inside the popup."""

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)
