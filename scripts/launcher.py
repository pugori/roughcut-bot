"""ChannelDNA Studio Native Launcher (Secure RAM Decryption & Desktop Web GUI).

1. Reads AES-256 encrypted payload ('app.enc').
2. Decrypts code and 2-Tab React UI bundle directly into a secure temporary runtime sandbox.
3. Automatically launches the local Desktop Web GUI in the user's default browser.
4. Keeps the session open until user exits.
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
import shutil
import traceback
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
    print(f"[*] 최신 보안 런타임 패키지(app.enc)를 다운로드하는 중입니다...", flush=True)
    try:
        req = urllib.request.Request(github_url, headers={"User-Agent": "ChannelDNA-Launcher/2.0"})
        with urllib.request.urlopen(req) as resp:
            return resp.read()
    except Exception as e:
        print(f"[!] 패키지 다운로드 실패: {e}", flush=True)
        raise FileNotFoundError("암호화 런타임 'app.enc'를 찾을 수 없습니다.")


def launch_in_memory():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        import subprocess
        print("[*] 필수 보안 모듈(cryptography)을 설정하는 중입니다...", flush=True)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "cryptography", "aiohttp"])
        from cryptography.fernet import Fernet

    print("=" * 60)
    print("🎬 ChannelDNA Studio v2.0 - 로컬 런처 시작")
    print("=" * 60)

    # 1. Load & Decrypt Payload in RAM
    enc_data = fetch_or_load_payload()
    cipher = Fernet(get_master_key())
    
    print("[*] 보안 런타임 복호화 중...", flush=True)
    decrypted_zip_bytes = cipher.decrypt(enc_data)

    # 2. Extract into temporary secure sandbox
    sandbox_dir = tempfile.mkdtemp(prefix="cdna_sandbox_")
    try:
        with zipfile.ZipFile(io.BytesIO(decrypted_zip_bytes)) as zf:
            zf.extractall(sandbox_dir)

        # Prepend to Python sys.path
        sys.path.insert(0, sandbox_dir)

        # 3. Launch Local Web Desktop GUI
        print("[*] ChannelDNA Studio 로컬 워크스페이스를 시작합니다...\n", flush=True)
        import run_local_gui
        run_local_gui.main()
    except Exception as e:
        print(f"\n[오류 발생] 프로그램 실행 중 문제가 발생했습니다: {e}", flush=True)
        traceback.print_exc()
        input("\n프로그램을 종료하려면 엔터 키를 누르세요...")
    finally:
        # Clean sandbox on exit
        if os.path.exists(sandbox_dir):
            try:
                shutil.rmtree(sandbox_dir, ignore_errors=True)
            except Exception:
                pass


if __name__ == "__main__":
    launch_in_memory()
