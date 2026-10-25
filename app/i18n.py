"""UI language: Chinese source strings, English translations.

tr("中文 {x}", x=...) returns the English text when the UI language is English, otherwise the
Chinese original. Untranslated strings fall back to Chinese. Language is chosen at startup
("system" follows the Windows display language) and changes apply after a restart, except
the result pages and tray menu, which pick up the new language immediately.
"""
from PySide6.QtCore import QLocale

LANG_LABELS = {"system": "跟随系统", "zh": "中文", "en": "English"}
_lang = "zh"


def resolve(setting):
    if setting in ("zh", "en"):
        return setting
    return "zh" if QLocale.system().language() == QLocale.Chinese else "en"


def set_language(setting):
    global _lang
    _lang = resolve(setting)
    return _lang


def lang():
    return _lang


def tr(s, **kw):
    text = EN.get(s, s) if _lang == "en" else s
    return text.format(**kw) if kw else text


EN = {
    # --- shared / names
    "、": ", ",
    "跟随系统": "Follow system",
    "中文": "中文",
    "亮色": "Light",
    "暗色": "Dark",
    "近义词 / 反义词": "Synonyms / antonyms",
    "例句（Tatoeba）": "Examples (Tatoeba)",
    "维基百科": "Wikipedia",
    "AI 翻译": "AI translation",
    "未知显示器": "Unknown display",
    # anchors
    "左上": "Top left", "上中": "Top center", "右上": "Top right",
    "左中": "Middle left", "正中": "Center", "右中": "Middle right",
    "左下": "Bottom left", "下中": "Bottom center", "右下": "Bottom right",
    # --- tray
    "InstantDic 快捷查词": "InstantDic quick lookup",
    "打开查词窗口": "Open lookup window",
    "设置（词典、排序、快捷键）…": "Settings (dictionaries, order, hotkey)…",
    "主题": "Theme",
    "识别屏幕": "Identify screens",
    "重置窗口": "Reset window",
    "打开日志文件夹": "Open log folder",
    "退出": "Quit",
    "屏幕 {i}": "Screen {i}",
    # --- popup
    "拖动窗口": "Drag window",
    "后退 (Alt+←)": "Back (Alt+←)",
    "输入单词或句子，回车查询": "Type a word or sentence, press Enter",
    "固定窗口（失焦不隐藏）": "Pin window (don't hide when focus is lost)",
    # --- main / notifications
    "导入「{name}」失败：{err}": "Importing \"{name}\" failed: {err}",
    "{label} 下载失败：{err}\n下次启动会重试。": "Downloading {label} failed: {err}\nIt will be retried on next start.",
    # --- hotkeys
    "快捷键里只能有一个非修饰键：{text}": "A hotkey can have only one non-modifier key: {text}",
    "无法识别的按键：{part}": "Unrecognized key: {part}",
    "快捷键缺少主键：{text}": "The hotkey has no main key: {text}",
    "快捷键 {text} 已被其他程序占用（例如 EasyDict），请先关闭它或换一个快捷键。":
        "Hotkey {text} is already used by another program (e.g. EasyDict). Close it or choose another hotkey.",
    "注册快捷键 {text} 失败（错误码 {err}）。": "Registering hotkey {text} failed (error {err}).",
    # --- settings window
    "InstantDic 设置": "InstantDic Settings",
    "词典与排序": "Dictionaries and order",  # no "&": Qt treats it as a mnemonic
    "常规": "General",
    "勾选=启用；拖动调整查词结果中的先后顺序。": "Checked = enabled. Drag to change the order of sections in results.",
    "导入词典…": "Import dictionary…",
    "重命名": "Rename",
    "默认折叠/展开": "Collapse by default",
    "重建索引": "Rebuild index",
    "移除": "Remove",
    "（正在建立索引…）": " (indexing…)",
    "（正在下载数据…）": " (downloading data…)",
    "（错误：{err}）": " (error: {err})",
    "（默认折叠）": " (collapsed by default)",
    "（{msg}…）": " ({msg}…)",
    "选择要导入的 MDX 词典": "Choose MDX dictionaries to import",
    "MDict 词典 (*.mdx)": "MDict dictionaries (*.mdx)",
    "显示名称：": "Display name:",
    "内置项目不能移除，取消勾选即可停用。": "Built-in sections can't be removed; uncheck them to disable.",
    "移除词典": "Remove dictionary",
    "从列表中移除「{name}」？\n（不会删除词典文件本身）": "Remove \"{name}\" from the list?\n(The dictionary files themselves are not deleted.)",
    "只在本地词典查不到时调用（或手动点结果页底部的「用 AI 翻译」）。":
        "Used only when no local dictionary has the word (or when you click \"Translate with AI\" at the bottom of results).",
    "粘贴任意厂商的 API Key，会自动识别服务商": "Paste an API key from any provider; it is detected automatically",
    "显示": "Show",
    "Key 保存在 Windows 凭据管理器中，不会写进配置文件。": "The key is stored in Windows Credential Manager, never in the config file.",
    "服务商": "Provider",
    "https://.../v1（OpenAI 兼容接口地址）": "https://.../v1 (OpenAI-compatible endpoint)",
    "接口地址": "Endpoint",
    "留空 = 首次使用时自动选择该厂商便宜、快速的模型": "Empty = pick this provider's cheap, fast model on first use",
    "获取模型列表": "Get model list",
    "模型": "Model",
    "词典查到时，在结果页底部显示「用 AI 翻译」按钮（点了才调用）":
        "When dictionaries find the word, show a \"Translate with AI\" button at the bottom (only calls AI when clicked)",
    "保存": "Save",
    "保存并测试": "Save and test",
    "无法从 Key 识别服务商，请手动选择；不在列表里的选「自定义」并填写接口地址。":
        "Couldn't detect the provider from this key. Pick it manually, or choose \"Custom\" and enter the endpoint.",
    "已识别为：{name}": "Detected: {name}",
    "这种格式的 Key 可能属于：{names}。已先选「{first}」，不对请手动改。":
        "Keys in this format may belong to: {names}. \"{first}\" is selected; change it if that's wrong.",
    "保存 API Key": "Save API key",
    "写入 Windows 凭据管理器失败：{e}": "Writing to Windows Credential Manager failed: {e}",
    "已保存。": "Saved.",
    "正在获取模型列表…": "Fetching model list…",
    "获取失败：{err}\n可以直接在「模型」里手动填写模型名。": "Fetch failed: {err}\nYou can type a model name into \"Model\" directly.",
    "共 {n} 个模型，已选择：{pick}（可在下拉框里改）": "{n} models; selected: {pick} (change it in the dropdown)",
    "正在测试…": "Testing…",
    "测试失败：{err}": "Test failed: {err}",
    "测试成功（模型 {model}）：\n{text}": "Test succeeded (model {model}):\n{text}",
    "界面语言": "Language",
    "（重启后完全生效）": "(fully applies after restart)",
    "例如 Ctrl+F12、Ctrl+Alt+D": "e.g. Ctrl+F12, Ctrl+Alt+D",
    "应用": "Apply",
    "唤出快捷键": "Hotkey",
    "提示：Win+空格 被系统占用，可用 AutoHotkey 把它映射到这里的快捷键。":
        "Tip: Win+Space is reserved by Windows; use AutoHotkey to map it to this hotkey.",
    "点击其他窗口时自动隐藏": "Hide when clicking another window",
    "弹出位置": "Popup position",
    "当前：{name}": "Current: {name}",
    "点击格子（或用方向键）\n选择窗口弹出的方位": "Click a cell (or use arrow keys)\nto choose where the window appears",
    "宽": "Width",
    "高": "Height",
    "离屏幕边缘": "Edge margin",
    "窗口大小": "Window size",
    "大小按逻辑像素计算，各屏幕缩放比例不同也会显示成同样大小；拖动窗口边缘也会自动保存。":
        "Sizes are in logical pixels, so the window looks the same on screens with different scaling. Dragging the window edge saves it too.",
    "开机自动启动": "Start with Windows",
    "鼠标所在的屏幕": "Screen under the mouse",
    "屏幕 {i}：{name}（{w}×{h}，{scale}%）": "Screen {i}: {name} ({w}×{h}, {scale}%)",
    "（之前选的屏幕当前未连接）": "(previously chosen screen is not connected)",
    "设置失败：{e}": "Failed: {e}",
    "快捷键": "Hotkey",
    "已设置为 {text}": "Set to {text}",
    # --- result pages
    "AI 正在翻译…": "AI is translating…",
    "出错了": "Something went wrong",
    "还没有导入词典。<br>右键托盘图标 → <b>设置</b> → <b>导入词典</b>，选择 .mdx 文件。":
        "No dictionaries yet.<br>Right-click the tray icon → <b>Settings</b> → <b>Import dictionary</b> and choose an .mdx file.",
    "输入单词后回车查询。": "Type a word and press Enter.",
    "本地词典中没有找到 <b>{q}</b>。<br>（AI 翻译已在设置中停用。）": "<b>{q}</b> was not found in local dictionaries.<br>(AI translation is disabled in Settings.)",
    "本地词典中没有找到 {q}": "{q} was not found in local dictionaries",
    "未找到 {q}，显示 <b>{word}</b> 的结果": "{q} not found; showing results for <b>{word}</b>",
    "用 AI 翻译": "Translate with AI",
    "AI 生成，仅供参考": "AI-generated, for reference only",
    "尚未设置 AI 翻译的 API Key。<br>右键托盘图标 → <b>设置</b> → <b>AI 翻译</b> 填写后即可使用。":
        "No API key set for AI translation.<br>Right-click the tray icon → <b>Settings</b> → <b>AI translation</b> to add one.",
    "{label} 正在下载，完成后即可使用。": "{label} is downloading and will be available when done.",
    "首次使用需要下载 {label}（{size}），已开始下载。": "{label} ({size}) must be downloaded first; the download has started.",
    "例句来源：Tatoeba（CC-BY 2.0 FR）": "Examples: Tatoeba (CC-BY 2.0 FR)",
    "近义": "Synonyms",
    "反义": "Antonyms",
    "来源：WordNet、Datamuse": "Sources: WordNet, Datamuse",
    "来源：维基百科（CC BY-SA）": "Source: Wikipedia (CC BY-SA)",
    # --- AI errors
    "尚未设置 AI 翻译的 API Key": "No API key set for AI translation",
    "无法获取模型列表，请在设置中手动填写模型名": "Couldn't fetch the model list; enter a model name in Settings",
    "没有找到可用的对话模型，请在设置中手动填写模型名": "No usable chat model found; enter a model name in Settings",
    "AI 没有返回内容": "The AI returned nothing",
    "API Key 无效，请在设置中检查（也可能是选错了服务商）": "Invalid API key; check it in Settings (or the provider may be wrong)",
    "账户余额不足": "Insufficient account balance",
    "没有权限使用该模型或接口": "No permission for this model or endpoint",
    "请求太频繁，请稍后再试": "Too many requests; try again later",
    "请求格式错误（模型名可能不对）": "Bad request (the model name may be wrong)",
    "接口地址或模型名不存在": "Endpoint or model not found",
    "请求超时": "Request timed out",
    "网络错误：{e}": "Network error: {e}",
    "尚未设置 API Key": "No API key set",
    "模型列表格式无法识别": "Unrecognized model list format",
    # --- dictionaries / datasets
    "该词典使用 LZO 压缩，暂不支持": "This dictionary uses LZO compression, which isn't supported yet",
    "未知压缩类型 {kind}": "Unknown compression type {kind}",
    "该词典已加密（需要注册码），无法读取": "This dictionary is encrypted (needs a registration code) and can't be read",
    "Tatoeba 中英例句": "Tatoeba English–Chinese examples",
    "WordNet 英文同义词库": "WordNet English thesaurus",
    "约 26 MB": "about 26 MB",
    "约 11 MB": "about 11 MB",
    "下载 {label} {pct}%": "Downloading {label} {pct}%",
    "对照表": "sentence links",
    "中文句子": "Chinese sentences",
    "英文句子": "English sentences",
    "建立例句索引": "Indexing examples",
    "读取 {name}": "Reading {name}",
    "建立索引": "Building index",
    # --- provider names
    "通义千问（阿里云百炼）": "Qwen (Alibaba Cloud Model Studio)",
    "Kimi（月之暗面）": "Kimi (Moonshot AI)",
    "智谱 GLM": "Zhipu GLM",
    "豆包（火山方舟）": "Doubao (Volcengine Ark)",
    "文心（百度千帆）": "ERNIE (Baidu Qianfan)",
    "硅基流动 SiliconFlow": "SiliconFlow",
    "自定义（OpenAI 兼容接口）": "Custom (OpenAI-compatible)",
}
