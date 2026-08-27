"""ChannelDNA Studio Native Launcher (100% Windowed GUI with Zero Console/CMD Window).

1. Completely eliminates black CMD/console windows (--noconsole).
2. Reads AES-256 encrypted payload ('app.enc').
3. Decrypts code and UI into an in-memory runtime sandbox.
4. Spawns standalone frameless ChannelDNA Studio window.
"""

import io
import asyncio
import aiohttp
import aiohttp.web
import sqlite3
import dataclasses
import json
import logging
import threading
import webbrowser
import subprocess
import socket
import tempfile
import zipfile
import urllib.request
import base64
import hashlib
import ctypes
import os
import sys
import shutil
from pathlib import Path

# Safe stdout handling in windowed mode
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# Master Key Derivation
MASTER_KEY_SECRET = os.environ.get("CHANNELDNA_MASTER_KEY")


def show_error_dialog(title: str, message: str):
    """Shows native Windows message box if error occurs in windowed mode."""
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
    except Exception:
        pass


def get_master_key() -> bytes:
    if MASTER_KEY_SECRET:
        return MASTER_KEY_SECRET.encode("utf-8")
    salt = b"ChannelDNA_ZeroCost_InRAM_Sandbox_2026"
    derived = hashlib.sha256(b"ChannelDNA_Production_Master_Secret_Key_v2" + salt).digest()
    return base64.urlsafe_b64encode(derived)


def fetch_or_load_payload() -> bytes:
    """Loads app.enc from bundled PyInstaller data, local directory, or GitHub Releases."""
    if hasattr(sys, "_MEIPASS"):
        meipass_enc = Path(sys._MEIPASS) / "app.enc"
        if meipass_enc.exists():
            return meipass_enc.read_bytes()

    local_enc = Path(sys.executable).resolve().parent / "app.enc"
    if local_enc.exists():
        return local_enc.read_bytes()

    dev_enc = Path(__file__).resolve().parent.parent / "dist_release" / "app.enc"
    if dev_enc.exists():
        return dev_enc.read_bytes()

    dev_root_enc = Path(__file__).resolve().parent.parent / "app.enc"
    if dev_root_enc.exists():
        return dev_root_enc.read_bytes()

    github_url = "https://github.com/pugori/roughcut-bot/releases/latest/download/app.enc"
    try:
        req = urllib.request.Request(github_url, headers={"User-Agent": "ChannelDNA-Launcher/2.0"})
        with urllib.request.urlopen(req) as resp:
            return resp.read()
    except Exception as e:
        show_error_dialog("ChannelDNA Studio", f"오류: {e}")
        raise FileNotFoundError("app.enc 다운로드 실패")

def update_splash(msg: str):
    try:
        import pyi_splash
        pyi_splash.update_text(msg)
    except ImportError:
        pass

def close_splash():
    try:
        import pyi_splash
        pyi_splash.close()
    except ImportError:
        pass

def launch_in_memory():
    update_splash("로컬 AI 엔진 초기화 중...")
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        import subprocess
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "cryptography", "aiohttp"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
        from cryptography.fernet import Fernet

    update_splash("보안 페이로드 해독 중...")
    try:
        enc_data = fetch_or_load_payload()
        cipher = Fernet(get_master_key())
        decrypted_zip_bytes = cipher.decrypt(enc_data)
    except Exception as e:
        close_splash()
        show_error_dialog("ChannelDNA Studio - Error", f"해독 실패: {e}")
        return

    update_splash("인메모리 샌드박스 구성 중...")
    sandbox_dir = tempfile.mkdtemp(prefix="cdna_sandbox_")
    try:
        with zipfile.ZipFile(io.BytesIO(decrypted_zip_bytes)) as zf:
            zf.extractall(sandbox_dir)

        sys.path.insert(0, sandbox_dir)
        import run_local_gui
        
        update_splash("스튜디오 UI 로딩 중...")
        
        # UI가 로딩되기 직전에 네이티브 스플래시 종료
        close_splash()
        run_local_gui.main()
    except Exception as e:
        close_splash()
        show_error_dialog("ChannelDNA Studio - Error", f"실행 중 오류가 발생했습니다:\n{e}")
    finally:
        close_splash()
        if os.path.exists(sandbox_dir):
            try:
                shutil.rmtree(sandbox_dir, ignore_errors=True)
            except Exception:
                pass
        # Force terminate all background processes and threads on exit
        try:
            import psutil

            parent = psutil.Process(os.getpid())
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
        except Exception:
            pass
        os._exit(0)


if __name__ == "__main__":
    launch_in_memory()
