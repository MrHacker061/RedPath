# Build from this spec with the pinned desktop extras on Windows 11 x64.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).parent
packages = ("redpath", "redpath_ai", "redpath_kali", "redpath_setup")
datas = [(str(path), "frontend") for path in sorted((root / "frontend").iterdir())
         if path.suffix in {".html", ".js", ".css"}]
hiddenimports = []
for package in packages:
    datas += collect_data_files(package)
    hiddenimports += collect_submodules(package)
# Uvicorn and pywebview select these modules dynamically at runtime.
hiddenimports += ["uvicorn.logging", "uvicorn.loops.asyncio", "uvicorn.protocols.http.h11_impl",
                  "uvicorn.protocols.websockets.websockets_impl", "uvicorn.lifespan.on",
                  "webview", "webview.platforms.edgechromium", "webview.platforms.winforms"]
a = Analysis([str(root / "redpath" / "desktop.py")], pathex=[str(root)],
             binaries=[], datas=sorted(datas), hiddenimports=sorted(set(hiddenimports)),
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="RedPath", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="RedPath")
