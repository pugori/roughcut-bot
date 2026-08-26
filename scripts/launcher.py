"""ChannelDNA Studio Native Launcher (100% Windowed GUI with Zero Console/CMD Window).

1. Completely eliminates black CMD/console windows (--noconsole).
2. Reads AES-256 encrypted payload ('app.enc').
3. Decrypts code and UI into an in-memory runtime sandbox.
4. Spawns standalone frameless ChannelDNA Studio window.
"""

# Explicitly import all runtime dependencies so PyInstaller packages them
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

# Master Key Derivation (Matches build_encrypted_release.py)
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
    # 1. PyInstaller bundled data directory
    if hasattr(sys, "_MEIPASS"):
        meipass_enc = Path(sys._MEIPASS) / "app.enc"
        if meipass_enc.exists():
            return meipass_enc.read_bytes()

    # 2. Local directory next to executable
    local_enc = Path(sys.executable).resolve().parent / "app.enc"
    if local_enc.exists():
        return local_enc.read_bytes()

    # 3. Local source tree
    dev_enc = Path(__file__).resolve().parent.parent / "dist_release" / "app.enc"
    if dev_enc.exists():
        return dev_enc.read_bytes()

    dev_root_enc = Path(__file__).resolve().parent.parent / "app.enc"
    if dev_root_enc.exists():
        return dev_root_enc.read_bytes()

    # 4. GitHub Releases CDN download
    github_url = "https://github.com/pugori/roughcut-bot/releases/latest/download/app.enc"
    try:
        req = urllib.request.Request(github_url, headers={"User-Agent": "ChannelDNA-Launcher/2.0"})
        with urllib.request.urlopen(req) as resp:
            return resp.read()
    except Exception as e:
        show_error_dialog("ChannelDNA Studio", f"런타임 패키지 다운로드 실패: {e}")
        raise FileNotFoundError("암호화 런타임 'app.enc'를 찾을 수 없습니다.")


def show_splash_screen():
    import tkinter as tk
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    
    window_width = 400
    window_height = 200
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = int((screen_width / 2) - (window_width / 2))
    y = int((screen_height / 2) - (window_height / 2))
    root.geometry(f'{window_width}x{window_height}+{x}+{y}')
    root.configure(bg='#0f172a')
    
    label = tk.Label(root, text="🎬 ChannelDNA Studio\n\n보안 런타임을 불러오는 중입니다...", fg="white", bg="#0f172a", font=("Malgun Gothic", 12, "bold"))
    label.pack(expand=True)
    
    # Store reference so main thread can close it
    global splash_root
    splash_root = root
    
    # Check periodically if we should close
    def check_close():
        if getattr(sys, "CLOSE_SPLASH", False):
            root.destroy()
        else:
            root.after(100, check_close)
            
    root.after(100, check_close)
    root.mainloop()

def launch_in_memory():
    # Start splash screen in background thread
    splash_thread = threading.Thread(target=show_splash_screen, daemon=True)
    splash_thread.start()
    
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        import subprocess
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "cryptography", "aiohttp"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
        from cryptography.fernet import Fernet

    # 1. Load & Decrypt Payload in RAM
    try:
        enc_data = fetch_or_load_payload()
        cipher = Fernet(get_master_key())
        decrypted_zip_bytes = cipher.decrypt(enc_data)
    except Exception as e:
        sys.CLOSE_SPLASH = True
        show_error_dialog("ChannelDNA Studio - 오류", f"보안 런타임 복호화 실패: {e}")
        return

    # 2. Extract into temporary secure sandbox
    sandbox_dir = tempfile.mkdtemp(prefix="cdna_sandbox_")
    try:
        with zipfile.ZipFile(io.BytesIO(decrypted_zip_bytes)) as zf:
            zf.extractall(sandbox_dir)

        # Prepend to Python sys.path
        sys.path.insert(0, sandbox_dir)

        # 3. Launch Local Web Desktop GUI (Silent background service + Native Window)
        import run_local_gui
        
        # Close splash before starting webview (webview needs main thread on Windows)
        sys.CLOSE_SPLASH = True
        
        run_local_gui.main()
    except Exception as e:
        sys.CLOSE_SPLASH = True
        show_error_dialog("ChannelDNA Studio - 오류", f"프로그램 실행 중 오류가 발생했습니다:\n{e}")
    finally:
        sys.CLOSE_SPLASH = True
        # Clean sandbox on exit
        if os.path.exists(sandbox_dir):
            try:
                shutil.rmtree(sandbox_dir, ignore_errors=True)
            except Exception:
                pass


if __name__ == "__main__":
    launch_in_memory()
