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
        'cryptography', 'cryptography.fernet', 'shutil', 'pathlib'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchaudio', 'torchvision', 'cv2', 'pandas', 'scipy', 'numba', 
        'llvmlite', 'ctranslate2', 'faster_whisper', 'kiwipiepy', 'demucs',
        'matplotlib', 'IPython', 'pytest', 'PIL'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
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
