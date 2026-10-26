# Third-party notices

## Data downloaded or queried at runtime (not bundled)

| Source | Used for | License / terms |
|---|---|---|
| [Tatoeba](https://tatoeba.org/) | English–Chinese example sentences | CC BY 2.0 FR. Sentences are shown with a "Tatoeba" attribution line. |
| [Princeton WordNet 3.0](https://wordnet.princeton.edu/) (via the NLTK data package) | Synonyms, antonyms, sense glosses | WordNet 3.0 license (permissive, attribution required) |
| [Datamuse API](https://www.datamuse.com/api/) | Additional synonyms / antonyms | Free API, no key. Usage is subject to Datamuse's terms. |
| [Wikipedia](https://www.wikipedia.org/) REST API | Encyclopedia summaries | Text CC BY-SA 4.0. Each summary links to its article. |
| AI providers (DeepSeek, Qwen, Kimi, GLM, Doubao, ERNIE, SiliconFlow, OpenAI, Anthropic, Gemini, xAI, Mistral, Groq, OpenRouter, or any OpenAI-compatible API) | AI translation fallback with the user's own key | Each provider's terms of service |

Dictionaries (.mdx/.mdd) are **not** distributed with this project. Users import their own.

## Bundled software

| Component | License |
|---|---|
| [Qt for Python (PySide6)](https://doc.qt.io/qtforpython/), including Qt WebEngine (Chromium) and Qt Multimedia (FFmpeg) | LGPL-3.0 |
| [keyring](https://github.com/jaraco/keyring) | MIT |
| [NLTK](https://www.nltk.org/) | Apache-2.0 |
| [LemmInflect](https://github.com/bjascob/LemmInflect) | MIT |
| [opencc-python-reimplemented](https://github.com/yichen0831/opencc-python) (OpenCC dictionaries) | Apache-2.0 |
| [NumPy](https://numpy.org/) (LemmInflect dependency) | BSD-3-Clause |
| `app/_ripemd128.py`, vendored from [writemdict](https://github.com/zhansliu/writemdict) | MIT |

The popup's native frameless resizing (`WS_THICKFRAME` + `WM_NCCALCSIZE` + `WM_NCHITTEST`) follows the technique used by
[PyQt-Frameless-Window](https://github.com/zhiyiYo/PyQt-Frameless-Window) (LGPLv3). It is reimplemented in `app/winevents.py`; no code is copied.
