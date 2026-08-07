# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

# hiddenimports only — no datas: bundling .py files as data (what collect_all
# does) doubles the exe for nothing.
hiddenimports = []
for pkg in ('textual', 'rich', 'markdown_it'):
    # textual.demo hair drags in the whole httpx/click/http stack; the app
    # never imports it, so drop the package's demo submodules.
    hiddenimports += [m for m in collect_submodules(pkg) if not m.split('.')[1:2] == ['demo']]

a = Analysis(
    ['winget_tui\\cli.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # demo is the only importer of the HTTP stack, so these never graph either.
    excludes=['numpy', 'PIL', 'anyio', 'matplotlib', 'pandas', 'scipy', 'cv2', 'tkinter',
              'unittest', 'pydoc', 'doctest', 'xmlrpc', 'http.server', 'distutils',
              'textual.demo', 'httpx', 'httpcore', 'click', 'h11', 'h2', 'hpack', 'hyperframe', 'socksio', 'idna'],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='winget-tui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    icon='winget-tui.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)