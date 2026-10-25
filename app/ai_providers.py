"""AI providers. All are reached through their OpenAI-compatible chat API, so one client works for
every vendor; a provider only supplies the base URL, how to recognise its keys, and which models
to prefer (the cheapest fast one — translation needs no frontier model)."""
import re

# id -> (label, base_url, model preference hints in order)
PROVIDERS = {
    "deepseek":    ("DeepSeek",              "https://api.deepseek.com",                                 ["flash", "chat"]),
    "qwen":        ("通义千问（阿里云百炼）", "https://dashscope.aliyuncs.com/compatible-mode/v1",        ["qwen-flash", "qwen-turbo", "qwen-plus"]),
    "moonshot":    ("Kimi（月之暗面）",       "https://api.moonshot.cn/v1",                               ["turbo", "8k", "kimi"]),
    "zhipu":       ("智谱 GLM",              "https://open.bigmodel.cn/api/paas/v4",                     ["flash", "air"]),
    "doubao":      ("豆包（火山方舟）",       "https://ark.cn-beijing.volces.com/api/v3",                 ["lite", "flash", "pro"]),
    "qianfan":     ("文心（百度千帆）",       "https://qianfan.baidubce.com/v2",                          ["speed", "lite", "turbo"]),
    "siliconflow": ("硅基流动 SiliconFlow",   "https://api.siliconflow.cn/v1",                            ["Qwen", "DeepSeek"]),
    "openai":      ("OpenAI",                "https://api.openai.com/v1",                                ["nano", "mini"]),
    "anthropic":   ("Anthropic Claude",      "https://api.anthropic.com/v1",                             ["haiku"]),
    "gemini":      ("Google Gemini",         "https://generativelanguage.googleapis.com/v1beta/openai",  ["flash-lite", "flash"]),
    "xai":         ("xAI Grok",              "https://api.x.ai/v1",                                      ["mini", "fast"]),
    "mistral":     ("Mistral",               "https://api.mistral.ai/v1",                                ["small", "ministral"]),
    "groq":        ("Groq",                  "https://api.groq.com/openai/v1",                           ["instant", "llama"]),
    "openrouter":  ("OpenRouter",            "https://openrouter.ai/api/v1",                             ["flash", "mini", "haiku"]),
    "custom":      ("自定义（OpenAI 兼容接口）", "",                                                      []),
}

# (key pattern, candidate providers) — first match wins; several candidates means "ask the user".
_KEY_RULES = [
    (r"sk-ant-", ["anthropic"]),
    (r"sk-or-", ["openrouter"]),
    (r"gsk_", ["groq"]),
    (r"xai-", ["xai"]),
    (r"AIza", ["gemini"]),
    (r"sk-(proj|svcacct|admin)-", ["openai"]),
    (r"bce-v3/", ["qianfan"]),
    (r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", ["doubao"]),
    (r"[0-9a-f]{32}\.[A-Za-z0-9]{16}$", ["zhipu"]),
    (r"sk-[0-9a-f]{32}$", ["deepseek", "qwen"]),
    (r"sk-[a-z]{48}$", ["siliconflow"]),
    (r"sk-[A-Za-z0-9]{48}$", ["moonshot", "openai", "siliconflow"]),
    (r"[A-Za-z0-9]{32}$", ["mistral"]),
    (r"sk-", ["deepseek", "openai", "qwen", "moonshot", "siliconflow"]),
]

# Models that can't do chat completions; never auto-picked.
_NON_CHAT = re.compile(r"embed|whisper|tts|audio|realtime|dall-e|image|moderation|rerank|vision-only|transcribe|search",
                       re.I)


def label(pid):
    from .i18n import tr
    return tr(PROVIDERS.get(pid, PROVIDERS["custom"])[0])


def base_url(pid):
    return PROVIDERS.get(pid, PROVIDERS["custom"])[1]


def detect(key):
    """Likely providers for a pasted key, best guess first ([] if unrecognised)."""
    key = key.strip()
    for pattern, cands in _KEY_RULES:
        if re.match(pattern, key):
            return list(cands)
    return []


def pick_model(pid, models):
    """Cheapest-looking chat model by the provider's preference hints; None if nothing usable."""
    chat = [m for m in models if not _NON_CHAT.search(m)]
    for hint in PROVIDERS.get(pid, PROVIDERS["custom"])[2]:
        hits = sorted((m for m in chat if hint.lower() in m.lower()), key=len)
        if hits:
            return hits[0]
    return chat[0] if chat else None
