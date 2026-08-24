"""Utility script to package Discord Bot and SQLite Database for Oracle Cloud Deployment."""

import os
import shutil
import sys
import zipfile
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def create_oracle_deployment_bundle(output_zip: str = "oracle_cloud_bundle.zip"):
    base_dir = Path("C:/dna")
    bundle_path = base_dir / output_zip

    files_to_include = [
        "bot/discord_bot.py",
        "bot/config.py",
        "bot/__init__.py",
        "modal_app.py",
        "channel_dna.db",
        "requirements.txt",
        "scripts/oracle_setup.sh",
    ]

    dirs_to_include = [
        "channel_dna",
    ]

    print(f"📦 Creating Oracle Cloud Deployment Bundle: {bundle_path.name}...")
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for f in files_to_include:
            p = base_dir / f
            if p.exists():
                zipf.write(p, arcname=f)
                print(f"  + Added file: {f}")

        for d in dirs_to_include:
            dp = base_dir / d
            if dp.exists():
                for root, _, filenames in os.walk(dp):
                    for fn in filenames:
                        if fn.endswith((".py", ".json", ".sql", ".txt")) and "__pycache__" not in root:
                            full_path = Path(root) / fn
                            rel_path = full_path.relative_to(base_dir)
                            zipf.write(full_path, arcname=str(rel_path))
                print(f"  + Added directory: {d}")

    print(f"✓ Deployment bundle created successfully: {bundle_path.stat().st_size / 1024:.1f} KB")
    return bundle_path


if __name__ == "__main__":
    create_oracle_deployment_bundle()
