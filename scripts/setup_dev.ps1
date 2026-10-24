# Creates the dev environment outside OneDrive: %USERPROFILE%\.customdic\venv
# Uses a standalone CPython via uv, because Anaconda's bundled MSVC runtime breaks PySide6.
$root = "$env:USERPROFILE\.customdic"
python -m pip install -q --target "$root\uvtool" uv
$env:UV_PYTHON_INSTALL_DIR = "$root\python"
$env:UV_CACHE_DIR = "$root\uvcache"
$uv = "$root\uvtool\bin\uv.exe"
& $uv python install 3.12
& $uv venv --python 3.12 --managed-python "$root\venv"
& $uv pip install --python "$root\venv\Scripts\python.exe" -r "$PSScriptRoot\..\requirements.txt" pyinstaller
