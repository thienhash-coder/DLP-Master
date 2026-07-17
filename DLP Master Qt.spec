# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


bundled_binaries = [
    ('tools\\ffmpeg\\bin\\ffmpeg.exe', 'tools\\ffmpeg\\bin'),
    ('tools\\ffmpeg\\bin\\ffprobe.exe', 'tools\\ffmpeg\\bin'),
]

updater_exe = Path('dist') / 'DLP Master Updater.exe'
if updater_exe.exists():
    bundled_binaries.append((str(updater_exe), '.'))


a = Analysis(
    ['yt_dlp_qt_gui.py'],
    pathex=[],
    binaries=bundled_binaries,
    datas=[
        ('theme\\dark.qss', 'theme'),
        ('theme\\light.qss', 'theme'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DLP Master Qt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DLP Master Qt',
)
