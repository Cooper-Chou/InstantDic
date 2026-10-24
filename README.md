# InstantDic

一个只有「快捷查词窗口」的 Windows 词典：按快捷键弹出，输入即查。功能对标欧路词典的迷你查词窗，但不做主程序、生词本这些东西，保持简单。

- **本地 MDX/MDD 词典**：自己导入（牛津、朗文等），样式、图片、发音与原词典一致；朗文这类 Speex（.spx）发音会自动转码播放
- **AI 翻译兜底**：只在所有词典都查不到（或输入整句）时调用。支持 DeepSeek、通义千问、Kimi、智谱、豆包、文心、硅基流动、OpenAI、Claude、Gemini、Grok、Mistral、Groq、OpenRouter 及任意 OpenAI 兼容接口，粘贴 Key 自动识别服务商，流式输出，结果缓存，不重复花钱
- **例句 / 近反义词 / 维基百科**：Tatoeba 中英例句（离线）、WordNet + Datamuse、维基百科摘要。除 AI 翻译外不使用任何 AI
- **结果顺序可调**：每本词典、例句、近反义词、百科、AI 翻译都能拖动排序、停用、默认折叠
- **多显示器友好**：按显示器 EDID 而不是 Windows 编号识别屏幕，每次弹出重新计算位置和 DPI，睡眠唤醒、息屏后自动校正
- 亮色 / 暗色 / 跟随系统主题；联想输入；词形还原（went → go，looked up → look up）

## 安装

到 [Releases](../../releases) 下载，二选一：

- `InstantDic-Setup-x.y.z.exe`：安装版，带开始菜单快捷方式和开机自启选项。安装时可选「只为我安装」（不需要管理员权限）或「为所有用户安装」（装到 `C:\Program Files`）。
- `InstantDic-Portable-x.y.z.zip`：免安装版，解压后运行 `InstantDic\InstantDic.exe`。`InstantDic.exe` 必须和旁边的 `_internal` 文件夹放在一起。

两个版本的配置和数据都保存在同一个位置，可以互换。

首次使用：

1. 右键托盘图标 →「设置」→「导入词典…」，选择 `.mdx` 文件（同名 `.mdd` 会自动带上）。本项目**不附带任何词典**。
2. 「AI 翻译」页粘贴任意一家的 API Key（会自动识别服务商），模型可留空自动选择，也可点「获取模型列表」自己挑。Key 保存在 Windows 凭据管理器中。
3. 例句库（约 26 MB）和 WordNet（约 11 MB）会在首次启动时自动下载。

## 快捷键

默认唤出键是 `Ctrl+F12`，可在设置里修改。Win+空格 被 Windows 占用，无法直接注册；想用它可以借助 [AutoHotkey v2](https://www.autohotkey.com/)：

```ahk
#Space::SendInput "^{F12}"
```

也可以从命令行或脚本直接查词：`InstantDic.exe serendipity`（程序已在运行时会复用同一个窗口）。

## 数据位置

配置、索引、缓存、日志都在 `%LOCALAPPDATA%\InstantDic`。托盘菜单 →「打开日志文件夹」。

## 从源码运行 / 打包

需要 Python 3.12（**不要用 Anaconda 的 Python**：它自带的旧版 VC 运行库会让 PySide6 加载失败）。

```powershell
scripts\setup_dev.ps1      # 一次性：在 %USERPROFILE%\.instantdic 下建独立的 Python 和虚拟环境
scripts\build.ps1          # 打包到 %USERPROFILE%\.instantdic\build\dist\InstantDic，并重启程序
```

安装包由 [Inno Setup 6](https://jrsoftware.org/isinfo.php) 生成（`packaging/installer.iss`）。每次推送到 main，GitHub Actions 都会生成安装版和免安装版（在 Actions 页面下载）；推送 `v*` 标签则会自动发布 Release。

## 许可

代码采用 MIT 许可证，见 [LICENSE](LICENSE)。用到的数据和第三方组件见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
