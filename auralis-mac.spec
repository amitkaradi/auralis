# PyInstaller spec for Auralis on macOS. Run with:
#     pyinstaller auralis-mac.spec
# Output: dist/Auralis.app — a self-contained macOS application bundle that
# the build-mac.yml workflow then wraps into a .dmg with create-dmg.

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

import os as _os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

_datas = [
    ('assets/auralis.png', 'assets'),
    ('README.md',          '.'),
    ('LICENSE.txt',        '.'),
    # UI layer — Eel serves these via its own static file server.
    ('ui',                 'ui'),
]

# Same model bundling logic as Windows: if bundled_models/ exists, fold it
# into the .app so Auralis runs fully offline from first launch.
if _os.path.isdir('bundled_models'):
    _datas.append(('bundled_models', 'bundled_models'))
    print('[auralis-mac.spec] Bundling bundled_models/ — full .dmg build.')
else:
    print('[auralis-mac.spec] No bundled_models/ — lite .dmg build.')

# faster_whisper / av / ctranslate2 ship runtime data files that PyInstaller's
# static analyzer can't detect.
_datas += collect_data_files('faster_whisper')
_datas += collect_data_files('av')
_datas += collect_data_files('ctranslate2')
_datas += collect_data_files('huggingface_hub')
_datas += collect_data_files('tokenizers')
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
        # soundcard's macOS backend (Core Audio).
        'soundcard.coreaudio',
        'cffi',
        'faster_whisper',
        'ctranslate2',
        'tokenizers',
        'huggingface_hub',
        'av',
        'numpy',
        'model_manager',
        # Eel + bottle + gevent — picked up dynamically; declared explicitly
        # so PyInstaller bundles everything the Eel server needs.
        'eel',
        'bottle',
        'bottle_websocket',
        'gevent',
        'gevent.websocket',
        'geventwebsocket.handler',
        # Tkinter — used at runtime for the native file picker in import_wav.
        'tkinter',
        'tkinter.filedialog',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Per-app capture (pycaw / comtypes / process_loopback) is Windows-only;
    # explicitly exclude so PyInstaller doesn't complain about missing
    # imports on macOS. The Python code already handles `_process_loopback
    # is None` and pycaw ImportError gracefully.
    excludes=['matplotlib', 'scipy', 'pandas', 'tensorflow', 'torch',
              'pycaw', 'pycaw.pycaw', 'pycaw.constants',
              'comtypes', 'comtypes.client', 'process_loopback', 'psutil'],
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
    # macOS uses .icns rather than .ico; build_icons.py emits both.
    icon='assets/auralis.icns' if _os.path.exists('assets/auralis.icns') else None,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name='Auralis',
)
# BUNDLE wraps the COLLECT directory into a proper macOS .app bundle.
# The .app shows up as a normal application in Finder + Launchpad.
app = BUNDLE(
    coll,
    name='Auralis.app',
    icon='assets/auralis.icns' if _os.path.exists('assets/auralis.icns') else None,
    bundle_identifier='com.amitkaradi.auralis',
    version='1.1.1',
    info_plist={
        'CFBundleName':                'Auralis',
        'CFBundleDisplayName':         'Auralis',
        'CFBundleShortVersionString':  '1.1.1',
        'CFBundleVersion':             '1.1.1',
        'NSHighResolutionCapable':     True,
        # macOS prompts for these on first launch; the strings are shown
        # in the consent dialog.
        'NSMicrophoneUsageDescription':
            'Auralis transcribes microphone audio locally on your Mac.',
        'NSAudioCaptureUsageDescription':
            'Auralis transcribes system audio (e.g. Zoom, Chrome) locally on your Mac.',
        'LSMinimumSystemVersion':      '11.0',
    },
)
