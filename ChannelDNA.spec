# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

block_cipher = None

a = Analysis(
    ['scripts/launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=[('dist_release/app.enc', '.')],
    hiddenimports=[
        'asyncio', 'aiohttp', 'aiohttp.web', 'sqlite3', 'dataclasses',
        'json', 'logging', 'threading', 'webbrowser', 'subprocess', 'socket',
        'tempfile', 'zipfile', 'urllib.request', 'base64', 'hashlib', 'ctypes',
        'cryptography', 'cryptography.fernet', 'shutil', 'pathlib',
        'scipy', 'scipy.ndimage', 'scipy.signal', 'scipy.spatial',
        'faster_whisper', 'ctranslate2', 'kiwipiepy', 'librosa',
        'cv2', 'numpy', 'soundfile', 'sklearn', 'fastdtw', 'dtaidistance'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchaudio', 'torchvision', 'pandas', 
        'demucs', 'matplotlib', 'IPython', 'pytest', 'PIL'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

splash = Splash(
    'splash_screen.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(20, 360),
    text_size=11,
    text_color='#ffffff',
    minify_script=True,
    always_on_top=True
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ChannelDNA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='official_logo.ico',
    version='version_info.txt',
)

