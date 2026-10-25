"""Settings window ("Console"): result sources & order, theme, hotkey."""
import logging
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QSizePolicy, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from . import ai_providers, autostart
from .anchor_picker import AnchorPicker
from .config import section_name
from .dictionaries import INDEX_DIR, source_id_for
from .i18n import LANG_LABELS, tr
from .screens import ANCHOR_LABELS, ANCHORS, friendly_name, screen_ids
from .theme import THEME_LABELS

log = logging.getLogger(__name__)
ROLE_ID = Qt.UserRole
DATASET_SOURCE = {"examples": "examples", "wordnet": "thesaurus"}  # dataset -> result section it feeds


def default_name(path, title):
    t = (title or "").strip()
    if not t or "No HTML code allowed" in t or len(t) > 40:
        return Path(path).stem
    return t


class ConsoleWindow(QWidget):
    def __init__(self, ctl):
        super().__init__(None, Qt.Window)
        self.ctl = ctl
        self.setWindowTitle(tr("InstantDic 设置"))
        self.resize(560, 480)
        tabs = QTabWidget()
        tabs.addTab(self._build_sources_tab(), tr("词典与排序"))
        tabs.addTab(self._build_ai_tab(), tr("AI 翻译"))
        tabs.addTab(self._build_general_tab(), tr("常规"))
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        ctl.indexer.progress.connect(self._on_progress)
        ctl.indexer.finished.connect(lambda *_: self.refresh())
        ctl.datasets.progress.connect(lambda name, msg: self._on_progress(DATASET_SOURCE[name], msg))
        ctl.datasets.finished.connect(lambda *_: self.refresh())
        self.refresh()

    # ---------- sources ----------
    def _build_sources_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(tr("勾选=启用；拖动调整查词结果中的先后顺序。")))
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.model().rowsMoved.connect(self._save_order)
        self.list.itemChanged.connect(self._on_item_changed)
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, fn in [("导入词典…", self.import_dicts), ("重命名", self.rename), ("默认折叠/展开", self.toggle_collapsed),
                         ("重建索引", self.rebuild), ("移除", self.remove)]:
            b = QPushButton(tr(text))
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        return w

    def refresh(self):
        self.list.blockSignals(True)
        cur = self.list.currentRow()
        self.list.clear()
        for src in self.ctl.cfg.data["sources"]:
            label = section_name(src)
            if src["id"] in self.ctl.indexer.running:
                label += tr("（正在建立索引…）")
            elif any(DATASET_SOURCE[n] == src["id"] for n in self.ctl.datasets.running):
                label += tr("（正在下载数据…）")
            elif src.get("error"):
                label += tr("（错误：{err}）", err=src["error"])
            elif src.get("collapsed"):
                label += tr("（默认折叠）")
            it = QListWidgetItem(label)
            it.setData(ROLE_ID, src["id"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            it.setCheckState(Qt.Checked if src.get("enabled", True) else Qt.Unchecked)
            it.setToolTip(src.get("path", ""))
            self.list.addItem(it)
        self.list.setCurrentRow(min(cur, self.list.count() - 1))
        self.list.blockSignals(False)

    def _on_progress(self, sid, msg):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(ROLE_ID) == sid:
                self.list.blockSignals(True)
                it.setText(section_name(self._src(sid)) + tr("（{msg}…）", msg=msg))
                self.list.blockSignals(False)

    def _src(self, sid):
        return next(s for s in self.ctl.cfg.data["sources"] if s["id"] == sid)

    def _selected(self):
        it = self.list.currentItem()
        return self._src(it.data(ROLE_ID)) if it else None

    def _save_order(self, *_):
        by_id = {s["id"]: s for s in self.ctl.cfg.data["sources"]}
        self.ctl.cfg.data["sources"] = [by_id[self.list.item(i).data(ROLE_ID)] for i in range(self.list.count())]
        self.ctl.cfg.save()

    def _on_item_changed(self, it):
        src = self._src(it.data(ROLE_ID))
        enabled = it.checkState() == Qt.Checked
        if src.get("enabled", True) != enabled:
            src["enabled"] = enabled
            self.ctl.cfg.save()

    def import_dicts(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr("选择要导入的 MDX 词典"), "", tr("MDict 词典 (*.mdx)"))
        existing = {s["id"] for s in self.ctl.cfg.data["sources"]}
        for p in paths:
            p = os.path.abspath(p)
            sid = source_id_for(p)
            if sid in existing:
                continue
            src = {"id": sid, "type": "mdx", "name": Path(p).stem, "path": p, "enabled": True,
                   "collapsed": False, "named_by_user": False}
            # New dictionaries go after existing ones but before built-in sections (AI etc.).
            sources = self.ctl.cfg.data["sources"]
            pos = next((i for i, s in enumerate(sources) if s.get("type") != "mdx"), len(sources))
            sources.insert(pos, src)
            self.ctl.cfg.save()
            self.ctl.indexer.build(src)
        self.refresh()

    def rename(self):
        src = self._selected()
        if not src:
            return
        name, ok = QInputDialog.getText(self, tr("重命名"), tr("显示名称："), QLineEdit.Normal, section_name(src))
        if ok and name.strip():
            src.update(name=name.strip(), named_by_user=True)
            self.ctl.cfg.save()
            self.refresh()

    def toggle_collapsed(self):
        src = self._selected()
        if src:
            src["collapsed"] = not src.get("collapsed", False)
            self.ctl.cfg.save()
            self.refresh()

    def rebuild(self):
        src = self._selected()
        if src and src.get("type") == "mdx":
            self.ctl.indexer.build(src)
            self.refresh()

    def remove(self):
        src = self._selected()
        if not src:
            return
        if src.get("type") != "mdx":
            QMessageBox.information(self, tr("移除"), tr("内置项目不能移除，取消勾选即可停用。"))
            return
        if QMessageBox.question(self, tr("移除词典"), tr("从列表中移除「{name}」？\n（不会删除词典文件本身）", name=section_name(src))) \
                != QMessageBox.Yes:
            return
        self.ctl.cfg.data["sources"].remove(src)
        self.ctl.cfg.save()
        self.ctl.engine.close(src["id"])
        try:
            (INDEX_DIR / f"{src['id']}.sqlite").unlink(missing_ok=True)  # our own cache file, rebuildable
        except OSError:
            log.warning("could not delete index for %s", src["id"])
        self.refresh()

    # ---------- AI ----------
    def _build_ai_tab(self):
        from .ai import get_api_key
        w = QWidget()
        f = QFormLayout(w)
        ai = self.ctl.cfg.data["ai"]
        f.addRow(QLabel(tr("只在本地词典查不到时调用（或手动点结果页底部的「用 AI 翻译」）。")))

        key_row = QHBoxLayout()
        self.ai_key = QLineEdit(get_api_key())
        self.ai_key.setEchoMode(QLineEdit.Password)
        self.ai_key.setPlaceholderText(tr("粘贴任意厂商的 API Key，会自动识别服务商"))
        self.ai_key.textEdited.connect(self._on_key_edited)
        show = QPushButton(tr("显示"))
        show.setCheckable(True)
        show.toggled.connect(lambda v: self.ai_key.setEchoMode(QLineEdit.Normal if v else QLineEdit.Password))
        key_row.addWidget(self.ai_key, 1)
        key_row.addWidget(show)
        f.addRow("API Key", key_row)
        f.addRow("", QLabel(tr("Key 保存在 Windows 凭据管理器中，不会写进配置文件。")))

        self.ai_provider = QComboBox()
        for pid in ai_providers.PROVIDERS:
            self.ai_provider.addItem(ai_providers.label(pid), pid)
        self.ai_provider.setCurrentIndex(max(0, self.ai_provider.findData(ai.get("provider", "deepseek"))))
        self.ai_provider.currentIndexChanged.connect(self._on_provider_changed)
        f.addRow(tr("服务商"), self.ai_provider)
        self.ai_hint = QLabel("")
        self.ai_hint.setWordWrap(True)
        f.addRow("", self.ai_hint)

        self.ai_base = QLineEdit(ai.get("base_url") or ai_providers.base_url(ai.get("provider", "deepseek")))
        self.ai_base.setPlaceholderText(tr("https://.../v1（OpenAI 兼容接口地址）"))
        f.addRow(tr("接口地址"), self.ai_base)

        model_row = QHBoxLayout()
        self.ai_model = QComboBox()
        self.ai_model.setEditable(True)
        self.ai_model.lineEdit().setPlaceholderText(tr("留空 = 首次使用时自动选择该厂商便宜、快速的模型"))
        if ai.get("model"):
            self.ai_model.addItem(ai["model"])
        self.ai_model.setCurrentText(ai.get("model", ""))
        fetch = QPushButton(tr("获取模型列表"))
        fetch.clicked.connect(self._fetch_models)
        model_row.addWidget(self.ai_model, 1)
        model_row.addWidget(fetch)
        f.addRow(tr("模型"), model_row)

        self.ai_btn = QCheckBox(tr("词典查到时，在结果页底部显示「用 AI 翻译」按钮（点了才调用）"))
        self.ai_btn.setChecked(ai.get("show_button", True))
        f.addRow("", self.ai_btn)

        row = QHBoxLayout()
        save = QPushButton(tr("保存"))
        save.clicked.connect(self._save_ai)
        test = QPushButton(tr("保存并测试"))
        test.clicked.connect(self._test_ai)
        row.addWidget(save)
        row.addWidget(test)
        row.addStretch(1)
        f.addRow("", row)
        self.ai_status = QLabel("")
        self.ai_status.setWordWrap(True)
        self.ai_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addRow("", self.ai_status)
        return w

    def _on_key_edited(self, text):
        cands = ai_providers.detect(text)
        if not cands:
            self.ai_hint.setText(tr("无法从 Key 识别服务商，请手动选择；不在列表里的选「自定义」并填写接口地址。") if text.strip() else "")
            return
        self.ai_provider.setCurrentIndex(self.ai_provider.findData(cands[0]))
        if len(cands) == 1:
            self.ai_hint.setText(tr("已识别为：{name}", name=ai_providers.label(cands[0])))
        else:
            names = tr("、").join(ai_providers.label(c) for c in cands)
            self.ai_hint.setText(tr("这种格式的 Key 可能属于：{names}。已先选「{first}」，不对请手动改。",
                                    names=names, first=ai_providers.label(cands[0])))

    def _on_provider_changed(self):
        pid = self.ai_provider.currentData()
        if pid != "custom":
            self.ai_base.setText(ai_providers.base_url(pid))
        self.ai_model.clear()  # model names differ per vendor; re-picked on first use or via the list
        self.ai_model.setCurrentText("")

    def _save_ai(self):
        from .ai import set_api_key
        ai = self.ctl.cfg.data["ai"]
        pid = self.ai_provider.currentData()
        base = self.ai_base.text().strip()
        ai.update(provider=pid, base_url="" if base == ai_providers.base_url(pid) else base,
                  model=self.ai_model.currentText().strip(), show_button=self.ai_btn.isChecked())
        self.ctl.cfg.save()
        try:
            set_api_key(self.ai_key.text().strip())
        except Exception as e:
            QMessageBox.warning(self, tr("保存 API Key"), tr("写入 Windows 凭据管理器失败：{e}", e=e))
            return False
        self.ai_status.setText(tr("已保存。"))
        return True

    def _fetch_models(self):
        self._save_ai()
        self.ai_status.setText(tr("正在获取模型列表…"))

        def done(models, err):
            if err:
                self.ai_status.setText(tr("获取失败：{err}\n可以直接在「模型」里手动填写模型名。", err=err))
                return
            cur = self.ai_model.currentText()
            self.ai_model.clear()
            self.ai_model.addItems(models)
            pick = cur if cur in models else (ai_providers.pick_model(self.ai_provider.currentData(), models) or "")
            self.ai_model.setCurrentText(pick)
            self._save_ai()
            self.ai_status.setText(tr("共 {n} 个模型，已选择：{pick}（可在下拉框里改）", n=len(models), pick=pick))

        self.ctl.ai.list_models(done)

    def _test_ai(self):
        if not self._save_ai():
            return
        self.ai_status.setText(tr("正在测试…"))
        rid = self.ctl.ai.translate("serendipity")

        def on_update(r, text, state, err):
            if r != rid:
                return
            if state == "error":
                self.ai_status.setText(tr("测试失败：{err}", err=err))
            elif state == "done":
                self.ai_status.setText(tr("测试成功（模型 {model}）：\n{text}", model=self.ctl.ai.model(), text=text[:200]))
            if state in ("error", "done"):
                self.ctl.ai.update.disconnect(on_update)

        self.ctl.ai.update.connect(on_update)

    # ---------- general ----------
    def _build_general_tab(self):
        w = QWidget()
        f = QFormLayout(w)
        self.theme = QComboBox()
        for key, label in THEME_LABELS.items():
            self.theme.addItem(tr(label), key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(self.ctl.cfg.data.get("theme", "system"))))
        self.theme.currentIndexChanged.connect(lambda: self.ctl.set_theme(self.theme.currentData()))
        f.addRow(tr("主题"), self.theme)

        self.language = QComboBox()
        for key, label in LANG_LABELS.items():
            self.language.addItem(tr(label), key)
        self.language.setCurrentIndex(max(0, self.language.findData(self.ctl.cfg.data.get("language", "zh"))))
        self.language.currentIndexChanged.connect(lambda: self.ctl.set_language(self.language.currentData()))
        lang_row = QHBoxLayout()
        lang_row.addWidget(self.language, 1)
        lang_row.addWidget(QLabel(tr("（重启后完全生效）")))
        f.addRow(tr("界面语言"), lang_row)

        hk = QHBoxLayout()
        self.hotkey = QLineEdit(self.ctl.cfg.data["hotkey"])
        self.hotkey.setPlaceholderText(tr("例如 Ctrl+F12、Ctrl+Alt+D"))
        apply_btn = QPushButton(tr("应用"))
        apply_btn.clicked.connect(self._apply_hotkey)
        hk.addWidget(self.hotkey, 1)
        hk.addWidget(apply_btn)
        f.addRow(tr("唤出快捷键"), hk)
        f.addRow("", QLabel(tr("提示：Win+空格 被系统占用，可用 AutoHotkey 把它映射到这里的快捷键。")))

        self.blur = QCheckBox(tr("点击其他窗口时自动隐藏"))
        self.blur.setChecked(self.ctl.cfg.popup.get("hide_on_blur", True))
        self.blur.toggled.connect(lambda v: (self.ctl.cfg.popup.update(hide_on_blur=v), self.ctl.cfg.save()))
        f.addRow("", self.blur)

        p = self.ctl.cfg.popup
        self.pos_screen = QComboBox()
        ident = QPushButton(tr("识别屏幕"))
        ident.clicked.connect(self.ctl.tray.identify_screens)
        row = QHBoxLayout()
        row.addWidget(self.pos_screen, 1)
        row.addWidget(ident)
        f.addRow(tr("弹出位置"), row)

        self.pos_anchor = AnchorPicker(p.get("anchor", "top"))
        self.pos_anchor_label = QLabel()
        self.pos_anchor_label.setStyleSheet("color: palette(placeholder-text);")
        grid = QWidget()
        grid_row = QHBoxLayout(grid)
        grid_row.setContentsMargins(0, 2, 0, 2)
        grid_row.addWidget(self.pos_anchor, 0, Qt.AlignTop)
        side = QVBoxLayout()
        side.addWidget(self.pos_anchor_label)
        side.addWidget(QLabel(tr("点击格子（或用方向键）\n选择窗口弹出的方位")))
        side.addStretch(1)
        grid_row.addLayout(side)
        grid_row.addStretch(1)
        grid.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        f.addRow("", grid)
        self._update_anchor_label()

        self.pos_margin = self._spin(0, 400, p.get("margin", 40))
        self.pos_w = self._spin(320, 4000, p.get("width", 520))
        self.pos_h = self._spin(240, 4000, p.get("height", 640))
        size = QHBoxLayout()
        for label, sp in (("宽", self.pos_w), ("高", self.pos_h), ("离屏幕边缘", self.pos_margin)):
            size.addWidget(QLabel(tr(label)))
            size.addWidget(sp)
        size.addStretch(1)
        f.addRow(tr("窗口大小"), size)
        f.addRow("", QLabel(tr("大小按逻辑像素计算，各屏幕缩放比例不同也会显示成同样大小；拖动窗口边缘也会自动保存。")))
        self._fill_screens()
        self.pos_screen.currentIndexChanged.connect(self._save_placement)
        self.pos_screen.currentIndexChanged.connect(self._sync_picker_aspect)
        self.pos_anchor.anchorChanged.connect(lambda _: (self._update_anchor_label(), self._save_placement()))
        for sp in (self.pos_margin, self.pos_w, self.pos_h):
            sp.valueChanged.connect(self._save_placement)

        self.autostart = QCheckBox(tr("开机自动启动"))
        self.autostart.setChecked(autostart.is_enabled())
        self.autostart.toggled.connect(self._toggle_autostart)
        f.addRow("", self.autostart)
        return w

    @staticmethod
    def _spin(lo, hi, val):
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(int(val))
        return sp

    def _fill_screens(self):
        p = self.ctl.cfg.popup
        self.pos_screen.blockSignals(True)
        self.pos_screen.clear()
        self.pos_screen.addItem(tr("鼠标所在的屏幕"), "cursor")
        ids = screen_ids()
        for i, (sid, s) in enumerate(ids.items(), 1):
            g = s.size() * s.devicePixelRatio()
            self.pos_screen.addItem(tr("屏幕 {i}：{name}（{w}×{h}，{scale}%）", i=i, name=friendly_name(s), w=g.width(),
                                       h=g.height(), scale=f"{s.devicePixelRatio() * 100:.0f}"), "fixed:" + sid)
        if p.get("mode") == "fixed" and p.get("screen_id") not in ids:
            self.pos_screen.addItem(tr("（之前选的屏幕当前未连接）"), "fixed:" + p.get("screen_id", ""))
        cur = "cursor" if p.get("mode") != "fixed" else "fixed:" + p.get("screen_id", "")
        self.pos_screen.setCurrentIndex(max(0, self.pos_screen.findData(cur)))
        self.pos_screen.blockSignals(False)
        self._sync_picker_aspect()

    def _sync_picker_aspect(self, *_):
        """Draw the nine-cell picker in the shape of the chosen monitor (cursor mode: primary)."""
        mode, _, sid = (self.pos_screen.currentData() or "cursor").partition(":")
        s = screen_ids().get(sid) if mode == "fixed" else None
        s = s or QGuiApplication.primaryScreen()
        g = s.availableGeometry()
        self.pos_anchor.setAspect(g.width() / max(1, g.height()))

    def _update_anchor_label(self):
        self.pos_anchor_label.setText(tr("当前：{name}", name=tr(ANCHOR_LABELS[self.pos_anchor.anchor()])))

    def _save_placement(self, *_):
        mode, _, sid = self.pos_screen.currentData().partition(":")
        self.ctl.cfg.popup.update(mode=mode, screen_id=sid, anchor=self.pos_anchor.anchor(),
                                  margin=self.pos_margin.value(), width=self.pos_w.value(), height=self.pos_h.value())
        self.ctl.cfg.save()
        self.ctl.popup.on_screens_settled()

    def _toggle_autostart(self, on):
        try:
            autostart.set_enabled(on)
        except OSError as e:
            QMessageBox.warning(self, tr("开机自动启动"), tr("设置失败：{e}", e=e))

    def _apply_hotkey(self):
        text = self.hotkey.text().strip()
        err = self.ctl.set_hotkey(text)
        if err:
            QMessageBox.warning(self, tr("快捷键"), err)
        else:
            QMessageBox.information(self, tr("快捷键"), tr("已设置为 {text}", text=text))

    def show_window(self):
        self.refresh()
        self._fill_screens()
        self.show()
        self.raise_()
        self.activateWindow()
