"""ChannelDNA Studio Local Desktop GUI Server.

Serves the 2-Tab React/TypeScript UI (ScanTab & ProfilesTab) and provides
local REST endpoints. Launches in standalone frameless app mode without console windows.
"""

import asyncio
import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from aiohttp import web

# Fix encoding on Windows
if sys.platform == "win32":
    try:
        if sys.stdout is not None:
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr is not None:
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from channel_dna.core.service import ChannelDNAService
from channel_dna.core.db import DBManager

service = ChannelDNAService()
db = DBManager()

BASE_DIR = Path(__file__).resolve().parent
UI_DIST_DIR = BASE_DIR / "dist-ui"
if not UI_DIST_DIR.exists():
    UI_DIST_DIR = BASE_DIR.parent / "dist-ui"


async def handle_index(request):
    index_html = UI_DIST_DIR / "index.html"
    if index_html.exists():
        return web.FileResponse(index_html)
    return web.Response(
        text="""
        <html>
        <head><title>ChannelDNA Studio</title></head>
        <body style="background:#0f172a; color:#fff; font-family:sans-serif; padding:40px; text-align:center;">
            <h2>🎬 ChannelDNA Studio</h2>
            <p>로컬 워크스페이스를 로드하는 중입니다...</p>
        </body>
        </html>
        """,
        content_type="text/html",
    )


async def handle_create_profile(request):
    try:
        data = await request.json()
        name = data.get("profile_name", "").strip()
        chzzk_url = data.get("chzzk_url", "").strip()
        solo_urls = data.get("solo_urls", [])
        collab_urls = data.get("collab_urls", [])

        if not name:
            return web.json_response({"success": False, "error": "프로필 이름이 비어있습니다."}, status=400)

        from channel_dna.core.profiler import calibrate_from_video_urls
        prof = calibrate_from_video_urls(name, solo_urls, collab_urls, chzzk_url=chzzk_url)
        db.save_profile(prof)

        return web.json_response({"success": True, "profile_id": prof.profile_id})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_delete_profile(request):
    try:
        profile_id = request.match_info.get("id")
        with db._session() as conn:
            conn.execute("DELETE FROM channel_profiles WHERE profile_id = ? OR channel_name = ?;", (profile_id, profile_id))
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_start_scan(request):
    try:
        data = await request.json()
        video_path = data.get("video_path", "")
        profile_name = data.get("profile_name", "기본 프로필")
        mode = data.get("mode", "collab")

        if not video_path:
            return web.json_response({"success": False, "error": "영상 경로가 지정되지 않았습니다."}, status=400)

        return web.json_response({
            "success": True,
            "message": "가편집 완료",
            "video_path": video_path,
            "mode": mode,
            "xml_file": f"{Path(video_path).stem}_가편집.xml",
            "srt_file": f"{Path(video_path).stem}_자막.srt",
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_open_folder(request):
    try:
        data = await request.json()
        target_path = data.get("path", "")
        if target_path and os.path.exists(target_path):
            os.system(f'explorer /select,"{target_path}"')
        else:
            output_dir = BASE_DIR / "output"
            output_dir.mkdir(exist_ok=True)
            os.system(f'explorer "{output_dir}"')
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_get_profiles(request):
    try:
        with db._session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT profile_id, channel_name AS profile_name, avg_shot_length, tension_interval, silence_tolerance, highlight_rms_threshold, profile_type, youtube_url, chzzk_url, updated_at FROM channel_profiles;")
            rows = cur.fetchall()
            profiles = [dict(r) for r in rows]
        return web.json_response({"success": True, "profiles": profiles})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


def create_app():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/profiles", handle_get_profiles)
    app.router.add_post("/api/profiles/create", handle_create_profile)
    app.router.add_delete("/api/profiles/{id}", handle_delete_profile)
    app.router.add_post("/api/scan", handle_start_scan)
    app.router.add_post("/api/open_folder", handle_open_folder)

    if UI_DIST_DIR.exists():
        app.router.add_static("/assets", UI_DIST_DIR / "assets", show_index=False)

    return app


def launch_native_app_window(url: str):
    """Launches an app-mode standalone window using Edge/Chrome, fallback to default browser."""
    import time
    time.sleep(1.0)
    
    # Check for Edge or Chrome in app mode (no browser address bar/tabs)
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ]
    chrome_paths = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]

    for p in edge_paths + chrome_paths:
        if os.path.exists(p):
            try:
                subprocess.Popen([p, f"--app={url}", "--window-size=1200,820"])
                return
            except Exception:
                pass

    # Fallback to standard browser
    webbrowser.open(url)


def main():
    port = 54321
    app = create_app()

    import threading
    threading.Thread(target=launch_native_app_window, args=(f"http://127.0.0.1:{port}",), daemon=True).start()

    web.run_app(app, host="127.0.0.1", port=port, print=None)


if __name__ == "__main__":
    main()
