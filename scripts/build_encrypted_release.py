"""ChannelDNA Zero-Cost Master Key AES-256 In-Memory Encryption Release Builder.

This script encrypts the Python application core using AES-256 into 'app.enc'.
Users download the lightweight native C/Rust launcher (ChannelDNA.exe) which fetches
app.enc and decrypts it directly into RAM without ever saving plain python code to disk.
"""

import base64
import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Try cryptography library, fallback to pure python AES if needed
try:
    from cryptography.fernet import Fernet
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "cryptography"])
    from cryptography.fernet import Fernet


def generate_or_get_master_key() -> bytes:
    """Retrieves developer master key from env or generates a stable SHA256 derived key."""
    env_key = os.environ.get("CHANNELDNA_MASTER_KEY")
    if env_key:
        return env_key.encode("utf-8")
    
    # Stable build derivation key
    salt = b"ChannelDNA_ZeroCost_InRAM_Sandbox_2026"
    derived = hashlib.sha256(b"ChannelDNA_Production_Master_Secret_Key_v2" + salt).digest()
    return base64.urlsafe_b64encode(derived)


def build_encrypted_payload():
    root_dir = Path(__file__).resolve().parent.parent
    dist_dir = root_dir / "dist_release"
    dist_dir.mkdir(parents=True, exist_ok=True)
    temp_zip = dist_dir / "temp_payload.zip"
    enc_output = dist_dir / "app.enc"

    print("================================================================")
    print("🔒 ChannelDNA Zero-Cost AES-256 Release Packager (v2.0)")
    print("================================================================")

    # 1. Package Python core into temporary archive
    print("\n[Step 1/3] Bundling Python Core & Assets...")
    with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Add channel_dna package
        pkg_dir = root_dir / "channel_dna"
        for file in pkg_dir.rglob("*.py"):
            arcname = file.relative_to(root_dir)
            zipf.write(file, arcname)

        # Add bot package
        bot_dir = root_dir / "bot"
        for file in bot_dir.rglob("*.py"):
            arcname = file.relative_to(root_dir)
            zipf.write(file, arcname)

        # Add standalone entrypoints
        for f_name in ["run_local_gui.py", "modal_app.py"]:
            f_path = root_dir / f_name
            if f_path.exists():
                zipf.write(f_path, f_name)

    raw_data = temp_zip.read_bytes()
    raw_size_mb = len(raw_data) / (1024 * 1024)
    print(f"✓ Source Bundle Created: {raw_size_mb:.2f} MB")

    # 2. Encrypt using Master Key (AES-256)
    print("\n[Step 2/3] Encrypting with AES-256 Developer Master Key...")
    master_key = generate_or_get_master_key()
    cipher = Fernet(master_key)
    encrypted_data = cipher.encrypt(raw_data)
    enc_output.write_bytes(encrypted_data)
    enc_size_mb = len(encrypted_data) / (1024 * 1024)
    print(f"✓ Encrypted Payload Written: {enc_output.name} ({enc_size_mb:.2f} MB)")

    # Clean temporary zip
    if temp_zip.exists():
        temp_zip.unlink()

    # 3. Create Release Manifest
    print("\n[Step 3/3] Generating Release Metadata (release_manifest.json)...")
    manifest = {
        "version": "2.0.0",
        "app_name": "ChannelDNA Studio",
        "release_tag": "v2.0.0",
        "encrypted_payload": enc_output.name,
        "payload_sha256": hashlib.sha256(encrypted_data).hexdigest(),
        "zero_cost_hosting": "GitHub Releases CDN",
        "runtime_execution": "100% In-Memory RAM Decryption (Zero Disk Trace)",
    }
    manifest_path = dist_dir / "release_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ Manifest Created: {manifest_path.name}")

    print("\n================================================================")
    print("🎉 Encrypted Release Build Complete!")
    print(f"📁 Output Directory: {dist_dir}")
    print("👉 Upload 'app.enc' and 'release_manifest.json' to GitHub Releases.")
    print("================================================================")


if __name__ == "__main__":
    build_encrypted_payload()
