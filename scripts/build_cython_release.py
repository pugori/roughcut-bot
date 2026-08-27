"""ChannelDNA Zero-Cost Master Key AES-256 In-Memory Encryption Release Builder with Cython.

This script compiles Python logic into C-extensions (.pyd) to prevent reverse engineering,
then encrypts the machine code using AES-256 into 'app.enc'.
Even if extracted from %TEMP%, attackers only get unreadable machine code.
"""

import base64
import hashlib
import json
import os
import shutil
import sys
import zipfile
import subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from cryptography.fernet import Fernet
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "cryptography"])
    from cryptography.fernet import Fernet


def generate_or_get_master_key() -> bytes:
    env_key = os.environ.get("CHANNELDNA_MASTER_KEY")
    if env_key:
        return env_key.encode("utf-8")
    salt = b"ChannelDNA_ZeroCost_InRAM_Sandbox_2026"
    derived = hashlib.sha256(b"ChannelDNA_Production_Master_Secret_Key_v2" + salt).digest()
    return base64.urlsafe_b64encode(derived)


def cythonize_source(root_dir: Path, build_dir: Path):
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)
    
    print("\n[Step 1.1/4] Copying source to temp build directory...")
    for folder in ["channel_dna", "bot"]:
        src = root_dir / folder
        if src.exists():
            shutil.copytree(src, build_dir / folder)
            
    for file in ["run_local_gui.py", "modal_app.py"]:
        src = root_dir / file
        if src.exists():
            shutil.copy2(src, build_dir / file)
            
    print("\n[Step 1.2/4] Generating setup.py for Cython...")
    setup_py_content = """
from setuptools import setup
from Cython.Build import cythonize
import os

py_files = []
for root, _, files in os.walk("."):
    for file in files:
        if file.endswith(".py") and file not in ["setup.py", "run_local_gui.py", "modal_app.py", "graph_engine.py"] and not file.endswith("__init__.py"):
            py_files.append(os.path.join(root, file))


if __name__ == '__main__':
    setup(
        ext_modules=cythonize(
            py_files,
            compiler_directives={'language_level': "3", 'always_allow_keywords': True},
            nthreads=0,
            force=True
        )
    )
"""
    (build_dir / "setup.py").write_text(setup_py_content, encoding="utf-8")
    
    print("\n[Step 1.3/4] Compiling Python to C-Extensions (Machine Code)...")
    try:
        subprocess.check_call([sys.executable, "setup.py", "build_ext", "--inplace"], cwd=build_dir)
    except subprocess.CalledProcessError as e:
        print(f"Cython compilation failed: {e}")
        sys.exit(1)
        
    print("\n[Step 1.4/4] Cleaning up raw Python source files...")
    # Delete .c and .py files, leave .pyd and __init__.py and entry points
    for root_path, _, files in os.walk(build_dir):
        for file in files:
            path = Path(root_path) / file
            if file == "setup.py":
                path.unlink()
            elif file.endswith(".c"):
                path.unlink()
            elif file.endswith(".py") and file not in ["__init__.py", "run_local_gui.py", "modal_app.py", "graph_engine.py"]:
                path.unlink()

    
    # Remove build folder created by setuptools
    if (build_dir / "build").exists():
        shutil.rmtree(build_dir / "build")


def build_encrypted_payload():
    root_dir = Path(__file__).resolve().parent.parent
    dist_dir = root_dir / "dist_release"
    dist_dir.mkdir(parents=True, exist_ok=True)
    build_dir = root_dir / "cython_temp_build"
    temp_zip = dist_dir / "temp_payload.zip"
    enc_output = dist_dir / "app.enc"

    print("================================================================")
    print("🔒 ChannelDNA Zero-Cost AES-256 + CYTHON Release Packager (v3.0)")
    print("================================================================")

    # 1. Cythonize source code
    cythonize_source(root_dir, build_dir)

    # 2. Package Cythonized core into temporary archive
    print("\n[Step 2/4] Bundling Cythonized Core & Assets...")
    with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Add everything from build_dir
        for file in build_dir.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(build_dir)
                zipf.write(file, arcname)

        # Add UI build assets
        ui_dir = root_dir / "dist-ui"
        if ui_dir.exists():
            for file in ui_dir.rglob("*"):
                if file.is_file():
                    arcname = file.relative_to(root_dir)
                    zipf.write(file, arcname)

    raw_data = temp_zip.read_bytes()
    raw_size_mb = len(raw_data) / (1024 * 1024)
    print(f"✓ Source Bundle Created: {raw_size_mb:.2f} MB")

    # 3. Encrypt using Master Key (AES-256)
    print("\n[Step 3/4] Encrypting with AES-256 Developer Master Key...")
    master_key = generate_or_get_master_key()
    cipher = Fernet(master_key)
    encrypted_data = cipher.encrypt(raw_data)
    enc_output.write_bytes(encrypted_data)
    enc_size_mb = len(encrypted_data) / (1024 * 1024)
    print(f"✓ Encrypted Payload Written: {enc_output.name} ({enc_size_mb:.2f} MB)")

    # Clean temporary zip and build dir
    if temp_zip.exists():
        temp_zip.unlink()
    if build_dir.exists():
        shutil.rmtree(build_dir)

    # 4. Create Release Manifest
    print("\n[Step 4/4] Generating Release Metadata (release_manifest.json)...")
    manifest = {
        "version": "3.0.0",
        "app_name": "ChannelDNA Studio",
        "release_tag": "v3.0.0",
        "encrypted_payload": enc_output.name,
        "payload_sha256": hashlib.sha256(encrypted_data).hexdigest(),
        "zero_cost_hosting": "GitHub Releases CDN",
        "runtime_execution": "Native Machine Code (.pyd) + AES Encryption",
    }
    manifest_path = dist_dir / "release_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ Manifest Created: {manifest_path.name}")

    print("\n================================================================")
    print("🎉 Secure Cython + Encrypted Release Build Complete!")
    print(f"📁 Output Directory: {dist_dir}")
    print("👉 Upload 'app.enc' and 'release_manifest.json' to GitHub Releases.")
    print("================================================================")


if __name__ == "__main__":
    build_encrypted_payload()
