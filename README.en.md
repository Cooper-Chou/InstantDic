# InstantDic

[中文](README.md) | **English**

*Foreword: I really like Eudic (欧路词典), and I rely on its quick-lookup popup in particular. It's pretty much the only feature I use; I never touch the vocabulary book or select-to-translate. But maybe the app has trouble with window sizing: my computer has three monitors, and after the screens go to sleep and wake up, the quick-lookup window sometimes breaks. The rendered content no longer matches the window frame, and mouse clicks land in the wrong places. Later I tried an open-source app called EasyDict. It's polished and convenient, but parts of the experience still weren't quite what I wanted. So out of frustration I vibe-coded InstantDic. InstantDic is just a quick-lookup window: no vocabulary book, no select-to-translate or screenshot translation. Simple on purpose. Sharing it here for anyone who finds it useful. If you hit a bug, please open an issue.*



A Windows dictionary that is nothing but a quick-lookup popup: press a hotkey, type, read. It is modeled on Eudic's mini lookup window, without a main app, vocabulary book or the rest. Kept simple.

- **Local MDX/MDD dictionaries**: import your own (Oxford, Longman, …). Styles, images and pronunciations look and sound like the original. Speex (.spx) audio, as used by Longman, is transcoded automatically.
- **AI translation fallback**: called only when no dictionary has the word, or when you type a whole sentence. Works with DeepSeek, Qwen, Kimi, Zhipu GLM, Doubao, ERNIE, SiliconFlow, OpenAI, Claude, Gemini, Grok, Mistral, Groq, OpenRouter, or any OpenAI-compatible API. Paste a key and the provider is detected for you. Output streams in, and results are cached so a repeat lookup costs nothing.
- **Examples / synonyms & antonyms / Wikipedia**: Tatoeba English–Chinese example sentences (offline), WordNet + Datamuse, Wikipedia summaries. No AI is used anywhere except the translation fallback.
- **Your order**: every dictionary, examples, synonyms, Wikipedia and AI translation can be reordered by drag-and-drop, disabled, or collapsed by default.
- **Multi-monitor friendly**: screens are identified by their EDID, not by Windows' display numbers. Position and DPI are recomputed on every popup and corrected after sleep or screen-off.
- Chinese / English interface (picked from the Windows display language on first run, switchable in Settings); light / dark / follow-system theme; type-ahead suggestions; lemmatization (went → go, looked up → look up)

## Install

Download one of these from [Releases](../../releases):

- `InstantDic-Setup-x.y.z.exe`: installer, with a Start menu shortcut and a start-with-Windows option. You can install "for me only" (no admin rights) or "for all users" (into `C:\Program Files`).
- `InstantDic-Portable-x.y.z.zip`: portable version. Unzip and run `InstantDic\InstantDic.exe`. Keep `InstantDic.exe` next to its `_internal` folder.

Both versions keep settings and data in the same place, so you can switch between them freely.

First run:

1. Right-click the tray icon → Settings (设置) → Import dictionary (导入词典…), then pick an `.mdx` file. A `.mdd` file with the same name is picked up automatically. **No dictionaries are bundled** with this project.
2. On the AI translation (AI 翻译) tab, paste an API key from any supported provider; the provider is detected automatically. Leave the model empty to have one picked for you, or click "Get model list" (获取模型列表) to choose. The key is stored in Windows Credential Manager.
3. The example-sentence database (about 26 MB) and WordNet (about 11 MB) download automatically on first start.

The interface is available in Chinese and English. On first run it is Chinese if your Windows display language is Chinese and English otherwise; switch it any time under Settings → General → Language.

## Hotkey

The default hotkey is `Ctrl+F12`; you can change it in Settings. Win+Space is reserved by Windows and can't be registered directly. If you want it, map it with [AutoHotkey v2](https://www.autohotkey.com/):

```ahk
#Space::SendInput "^{F12}"
```

You can also look up a word from the command line or a script: `InstantDic.exe serendipity`. If the app is already running, it reuses the same window.

## Where data lives

Settings, indexes, caches and logs are all under `%LOCALAPPDATA%\InstantDic`. Tray menu → Open log folder (打开日志文件夹).

## Run from source / build

Requires Python 3.12. **Don't use Anaconda's Python**: its bundled, older VC++ runtime makes PySide6 fail to load.

```powershell
scripts\setup_dev.ps1      # one-time: standalone Python + virtualenv under %USERPROFILE%\.instantdic
scripts\build.ps1          # build into %USERPROFILE%\.instantdic\build\dist\InstantDic and restart the app
```

The installer is built with [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`packaging/installer.iss`). Every push to main makes GitHub Actions build the installer and the portable zip (downloadable from the Actions page). Pushing a `v*` tag also publishes a Release.

## License

The code is MIT-licensed; see [LICENSE](LICENSE). Data sources and third-party components are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Tip: get the Eudic-for-Mac quick-lookup experience

On a Mac, Eudic's quick-lookup window opens with Option+Space. To keep the same key habit on Windows, I use [AutoHotkey](https://github.com/AutoHotkey/AutoHotkey), an open-source key-remapping tool for Windows, to map **Win+Space** to InstantDic's hotkey **Ctrl+F12**. Pressing Win+Space then brings up the lookup window, with the same key position as on the Mac.

After installing AutoHotkey v2, create a `.ahk` file containing the line below and double-click it to run. To have it active at every login, put a shortcut to the file in your Startup folder (press `Win+R` and enter `shell:startup`).

```ahk
#Space::SendInput "^{F12}"
```

If you changed the hotkey in Settings, replace `^{F12}` accordingly (`^` is Ctrl, `!` is Alt, `+` is Shift).
