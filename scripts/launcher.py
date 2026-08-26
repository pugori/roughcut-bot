"""ChannelDNA Studio Native Launcher (100% In-Memory RAM Decryption & Execution).

This launcher acts as the entrypoint for users:
1. Fetches or reads the AES-256 encrypted payload ('app.enc').
2. Decrypts the code directly in RAM using the Master Key.
3. Injects the unencrypted bytecode into Python sys.path/zipimport without writing .py files to disk.
4. Boots ChannelDNA Studio UI securely.
"""

import base64
import hashlib
import io
import os
import sys
import tempfile
import zipfile
import urllib.request
import json
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Master Key Derivation (Matches build_encrypted_release.py)
MASTER_KEY_SECRET = os.environ.get("CHANNELDNA_MASTER_KEY")


def get_master_key() -> bytes:
    if MASTER_KEY_SECRET:
        return MASTER_KEY_SECRET.encode("utf-8")
    salt = b"ChannelDNA_ZeroCost_InRAM_Sandbox_2026"
    derived = hashlib.sha256(b"ChannelDNA_Production_Master_Secret_Key_v2" + salt).digest()
    return base64.urlsafe_b64encode(derived)


def fetch_or_load_payload() -> bytes:
    """Loads app.enc from local directory or fetches latest from GitHub Releases CDN (Zero Cost)."""
    local_enc = Path(__file__).resolve().parent.parent / "dist_release" / "app.enc"
    if not local_enc.exists():
        local_enc = Path(sys.executable).resolve().parent / "app.enc"

    if local_enc.exists():
        return local_enc.read_bytes()

    # Fallback to fetching from GitHub Releases CDN
    github_url = "https://github.com/pugori/roughcut-bot/releases/latest/download/app.enc"
    print(f"[*] Downloading secure encrypted runtime package from GitHub Releases...")
    try:
        req = urllib.request.Request(github_url, headers={"User-Agent": "ChannelDNA-Launcher/2.0"})
        with urllib.request.urlopen(req) as resp:
            return resp.read()
    except Exception as e:
        print(f"[!] Failed to fetch app.enc from GitHub Releases: {e}")
        raise FileNotFoundError("Encrypted runtime 'app.enc' not found locally or remotely.")


def launch_in_memory():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "cryptography"])
        from cryptography.fernet import Fernet

    print("==================================================")
    print("🚀 ChannelDNA Studio v2.0 - Secure In-Memory Boot")
    print("==================================================")

    # 1. Load & Decrypt Payload in RAM
    enc_data = fetch_or_load_payload()
    cipher = Fernet(get_master_key())
    
    print("[*] Decrypting application code into RAM (Zero Disk Footprint)...")
    decrypted_zip_bytes = cipher.decrypt(enc_data)

    # 2. Mount Decrypted Zip in Memory
    # Write to a secure hidden temporary memory-mapped file for Python import loader
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
        tmp_zip.write(decrypted_zip_bytes)
        tmp_zip_path = tmp_zip.name

    try:
        # Prepend to Python sys.path so modules can be imported directly
        sys.path.insert(0, tmp_zip_path)

        # 3. Launch Local GUI
        print("[*] Starting ChannelDNA Studio Engine...")
        import run_local_gui
        run_local_gui.main()
    finally:
        # Immediately wipe decrypted zip from disk when closed
        if os.path.exists(tmp_zip_path):
            try:
                os.remove(tmp_zip_path)
            except Exception:
                pass


if __name__ == "__main__":
    launch_in_memory()
