# PyInstaller spec for Auralis. Run with:  pyinstaller auralis.spec
# Output: dist\Auralis\Auralis.exe + a folder of dependencies. Inno Setup
# wraps that folder into a single installer.

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# build_release.bat decides whether to ship with or without the bundled
# Ivrit.AI v3 turbo model snapshot. Auto-detect by checking whether the
# bundled_models/ directory exists — this lets the same spec produce both
# the lite (no model) and full (model bundled) installers without edits.
import os as _os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

_datas = [
    ('assets/auralis.ico', 'assets'),
    ('assets/auralis.png', 'assets'),
    ('assets/splash.png',  'assets'),
    ('README.md',          '.'),
    ('LICENSE.txt',        '.'),
    # UI layer — Eel serves these via its own static file server. They must
    # ship with the EXE for the app to launch.
    ('ui',                 'ui'),
]
if _os.path.isdir('bundled_models'):
    _datas.append(('bundled_models', 'bundled_models'))
    print('[auralis.spec] Bundling bundled_models/ — full installer build.')
else:
    print('[auralis.spec] No bundled_models/ — lite installer build.')

# faster_whisper ships data files (silero_vad_v6.onnx, model assets) that
# PyInstaller's static analyzer doesn't detect because they're loaded
# dynamically at runtime. collect_data_files walks the installed package
# and grabs every non-Python file. Same for av/PyAV (ffmpeg DLLs) and
# ctranslate2 (C++ runtime DLLs).
_datas += collect_data_files('faster_whisper')
_datas += collect_data_files('av')
_datas += collect_data_files('ctranslate2')
_datas += collect_data_files('huggingface_hub')
_datas += collect_data_files('tokenizers')
# Eel ships its own /eel.js + websocket runtime that the front-end loads.
_datas += collect_data_files('eel')

_binaries = []
_binaries += collect_dynamic_libs('faster_whisper')
_binaries += collect_dynamic_libs('ctranslate2')
_binaries += collect_dynamic_libs('av')

a = Analysis(
    ['auralis.py'],
    pathex=[],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=[
        'soundcard',
        'soundcard.mediafoundation',
        'cffi',
        'faster_whisper',
        'ctranslate2',
        'tokenizers',
        'huggingface_hub',
        'av',
        'numpy',
        # New in v1.1: model catalog/downloader + per-app loopback.
        'model_manager',
        'process_loopback',
        'pycaw',
        'pycaw.pycaw',
        'pycaw.constants',
        'comtypes',
        'comtypes.client',
        'psutil',
        # Eel + bottle + gevent — picked up dynamically; declaring explicitly
        # so PyInstaller bundles everything the Eel server needs.
        'eel',
        'bottle',
        'bottle_websocket',
        'gevent',
        'gevent.websocket',
        'geventwebsocket.handler',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'pandas', 'tensorflow', 'torch'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Auralis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='assets/auralis.ico',
    version='version_info.txt',
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name='Auralis',
)
