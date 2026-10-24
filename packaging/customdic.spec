# PyInstaller spec: build with  pyinstaller packaging/customdic.spec --noconfirm
# Produces dist/CustomDic/CustomDic.exe (one-folder build: starts much faster than one-file with Qt WebEngine).
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = SPECPATH + "/.."

a = Analysis(
    [ROOT + "/customdic.pyw"],
    pathex=[ROOT],
    datas=collect_data_files("lemminflect") + collect_data_files("opencc") + [(ROOT + "/assets/icon.png", "assets")],
    hiddenimports=collect_submodules("keyring.backends") + ["nltk.corpus.reader.wordnet"],
    excludes=["tkinter", "matplotlib", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
              "PySide6.QtQuick3D", "PySide6.QtDesigner", "PySide6.QtBluetooth", "PySide6.QtSql"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="CustomDic", console=False,
          icon=ROOT + "/assets/icon.ico", version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="CustomDic")
