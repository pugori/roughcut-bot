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

from channel_dna_local.core.service import ChannelDNAService
from channel_dna_local.core.db import DBManager

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
            return web.json_response(
                {"success": False, "error": "프로필 이름이 비어있습니다."}, status=400
            )

        from channel_dna_local.core.profiler import ChannelProfiler

        profiler = ChannelProfiler(db=db)
        # Note: In local GUI, discord_user_id is not needed. The mock or real backend handles it.
        prof_res = profiler.calibrate_from_video_urls(
            solo_urls=solo_urls,
            collab_urls=collab_urls,
            profile_name=name,
            chzzk_channel_url=chzzk_url,
        )
        # In discord_bot.py, profiler.calibrate_from_video_urls saves to DB internally
        # and returns a dict with 'solo_profile' and 'collab_profile' info.
        # But wait, local GUI expects a prof object to pass to db.save_profile(prof).
        # Let's check prof_res to get the profile_id.
        profile_id = (
            prof_res.get("profile_id", name)
            if isinstance(prof_res, dict)
            else prof_res.profile_id if hasattr(prof_res, "profile_id") else name
        )

        return web.json_response({"success": True, "profile_id": profile_id})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_delete_profile(request):
    try:
        profile_id = request.match_info.get("id")
        with db._session() as conn:
            conn.execute(
                "DELETE FROM channel_profiles WHERE profile_id = ? OR channel_name = ? OR channel_name = ? OR channel_name = ?;",
                (profile_id, profile_id, f"{profile_id}_Solo", f"{profile_id}_Collab"),
            )
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_start_scan(request):
    try:
        data = await request.json()
        video_path = data.get("video_path", "").strip()
        profile_name = data.get("profile_name", "").strip()
        mode = data.get("mode", "collab")
        export_xml = data.get("export_xml", True)
        export_fcpxml = data.get("export_fcpxml", True)
        export_srt = data.get("export_srt", True)

        if not video_path:
            return web.json_response(
                {"success": False, "error": "영상 파일 경로가 지정되지 않았습니다."},
                status=400,
            )

        if not os.path.exists(video_path):
            return web.json_response(
                {
                    "success": False,
                    "error": f"지정된 영상 파일을 찾을 수 없습니다: {video_path}",
                },
                status=400,
            )

        if not profile_name or profile_name in ("기본 프로필", "Default"):
            return web.json_response(
                {
                    "success": False,
                    "error": "선택된 채널 프로필이 없습니다. 먼저 상단 [프로필 추출] 탭에서 채널 DNA 프로필을 생성해 주세요.",
                },
                status=400,
            )

        global scan_progress
        if scan_progress.get("status") == "running" and not scan_progress.get(
            "done", True
        ):
            return web.json_response(
                {"success": False, "error": "이미 다른 작업이 진행 중입니다."},
                status=429,
            )

        scan_progress = {
            "pct": 0,
            "status": "오디오 및 텐션 분석 시작 중...",
            "step_index": 1,
            "done": False,
            "error": "",
            "video_path": video_path,
        }

        def _scan_task():
            try:
                from channel_dna_local.core.pipeline import PipelineFacade

                pipeline = PipelineFacade()

                def progress_cb(step, pct, msg):
                    idx = 1
                    if (
                        "자막" in msg
                        or step == "SubtitleInit"
                        or step == "Transcription"
                    ):
                        idx = 2
                    elif step == "FCPXML":
                        idx = 3

                    scan_progress["step_index"] = idx
                    scan_progress["pct"] = int(pct * 100)
                    scan_progress["status"] = msg

                def on_complete(markers, subtitles):
                    out_dir = Path(video_path).parent

                    xml_path = out_dir / f"{Path(video_path).stem}.xml"
                    fcpxml_path = out_dir / f"{Path(video_path).stem}.fcpxml"
                    srt_path = out_dir / f"{Path(video_path).stem}_자막.srt"

                    if export_xml:
                        pipeline.exporter.export(
                            markers=markers,
                            vod_file_path=video_path,
                            output_path=str(xml_path),
                            export_format="xml",
                            fps=60.0,
                        )

                    if export_fcpxml:
                        pipeline.exporter.export(
                            markers=markers,
                            vod_file_path=video_path,
                            output_path=str(fcpxml_path),
                            export_format="fcpxml",
                            fps=60.0,
                        )

                    if subtitles and export_srt:
                        srt_base_path = out_dir / f"{Path(video_path).stem}_자막.srt"

                        # Remap subtitles to match the cut sequence timeline
                        subtitles = (
                            pipeline.subtitle_engine.remap_subtitles_to_sequence(
                                markers, subtitles
                            )
                        )
                        pipeline.subtitle_engine.export_srt_by_speakers(
                            subtitles, str(srt_base_path)
                        )
                    scan_progress["pct"] = 100
                    scan_progress["done"] = True
                    scan_progress["status"] = "완료"

                def on_error(e):
                    scan_progress["error"] = str(e)
                    scan_progress["status"] = "error"

                expected_dur = None
                try:
                    import cv2

                    cap = cv2.VideoCapture(video_path)
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    if fps > 0 and frames > 0:
                        expected_dur = frames / fps
                    cap.release()
                except:
                    pass

                pipeline.run_scan_worker(
                    vod_path=video_path,
                    channel_name=profile_name,
                    scan_mode=mode,
                    progress_cb=progress_cb,
                    on_complete=on_complete,
                    on_error=on_error,
                    expected_duration_sec=expected_dur,
                )
            except Exception as e:
                scan_progress["error"] = str(e)
                scan_progress["status"] = "error"

        import threading

        t = threading.Thread(target=_scan_task, daemon=True)
        t.start()

        return web.json_response(
            {
                "success": True,
                "message": "가편집 시작",
                "video_path": video_path,
                "mode": mode,
            }
        )
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_open_folder(request):
    try:
        data = await request.json()
        target_path = data.get("path", "")
        if target_path and os.path.exists(target_path):
            if os.path.isfile(target_path):
                os.system(f'explorer /select,"{target_path}"')
            else:
                os.system(f'explorer "{target_path}"')
        else:
            global scan_progress
            last_path = scan_progress.get("video_path", "")
            if last_path and os.path.exists(last_path):
                os.system(f'explorer /select,"{last_path}"')
            else:
                os.system(f'explorer "{BASE_DIR}"')
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_get_profiles(request):
    try:
        with db._session() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT profile_id, channel_name AS profile_name, avg_shot_length, tension_interval, silence_tolerance, highlight_rms_threshold, profile_type, youtube_url, chzzk_url, updated_at FROM channel_profiles;"
            )
            rows = cur.fetchall()

            # Group by base channel name so UI only shows 1 entry per streamer
            grouped = {}
            for r in rows:
                d = dict(r)
                pname = d["profile_name"] or ""
                # Strip _Solo and _Collab suffixes for display grouping
                if pname.endswith("_Solo"):
                    pname = pname[:-5]
                elif pname.endswith("_Collab"):
                    pname = pname[:-7]

                if not pname.strip() or "기본 프로필" in pname:
                    continue

                if pname not in grouped:
                    d["profile_name"] = pname
                    d["profile_id"] = pname  # UI uses profile_id to delete/select
                    grouped[pname] = d

            profiles = list(grouped.values())
        return web.json_response({"success": True, "profiles": profiles})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


# Global state for progress
engine_download_progress = {"pct": 0, "status": "대기 중"}
scan_progress = {
    "pct": 0,
    "status": "대기 중",
    "step_index": 1,
    "done": False,
    "error": "",
}


async def handle_download_engine(request):
    """Starts background download of AI Engine (mocked for now)."""
    global engine_download_progress
    engine_download_progress = {"pct": 0, "status": "downloading"}

    def _download_task():
        import time

        # TODO: Replace with actual HuggingFace zip download logic
        # url = "https://huggingface.co/datasets/.../AI_Engine.zip"
        for i in range(1, 11):
            time.sleep(0.5)
            engine_download_progress["pct"] = i * 10
        engine_download_progress["status"] = "done"

    import threading

    threading.Thread(target=_download_task, daemon=True).start()
    return web.json_response({"success": True})


async def handle_get_download_progress(request):
    return web.json_response(engine_download_progress)


async def handle_get_scan_progress(request):
    return web.json_response(scan_progress)


def create_app():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/profiles", handle_get_profiles)
    app.router.add_post("/api/profiles/create", handle_create_profile)
    app.router.add_delete("/api/profiles/{id}", handle_delete_profile)
    app.router.add_post("/api/scan", handle_start_scan)
    app.router.add_get("/api/scan/progress", handle_get_scan_progress)
    app.router.add_post("/api/download_engine", handle_download_engine)
    app.router.add_get("/api/download_engine/progress", handle_get_download_progress)
    app.router.add_post("/api/open_folder", handle_open_folder)

    if UI_DIST_DIR.exists():
        app.router.add_static("/assets", UI_DIST_DIR / "assets", show_index=False)

    return app


def start_server(app, port):
    import asyncio

    # aiohttp requires its own event loop in the background thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    web.run_app(app, host="127.0.0.1", port=port, print=None, loop=loop)


def main():
    import socket
    import threading
    import os
    import webview

    # 1. 상용 프로그램 수준의 포트 충돌 원천 차단 (동적 여유 포트 할당)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    app = create_app()

    # 2. 백그라운드 스레드에서 REST API 서버 구동
    server_thread = threading.Thread(target=start_server, args=(app, port), daemon=True)
    server_thread.start()

    class Api:
        def select_file(self):
            import webview

            file_types = (
                "Video files (*.mp4;*.mkv;*.mov;*.avi;*.ts)",
                "All files (*.*)",
            )
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types
            )
            if result and len(result) > 0:
                return result[0]
            return ""

    # 3. 브라우저가 아닌 완벽한 독립 데스크톱 네이티브 윈도우 생성 (상용 프로그램 퀄리티)
    window = webview.create_window(
        "ChannelDNA Studio Pro",
        f"http://127.0.0.1:{port}",
        width=1200,
        height=820,
        resizable=True,
        text_select=False,
        js_api=Api(),
    )

    def on_closed():
        # 창 종료 시 모든 백그라운드 프로세스(FFmpeg, 워커 스레드 등) 즉시 강제 종료
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

    window.events.closed += on_closed

    # 윈도우가 닫힐 때까지 블로킹 (UI 루프)
    webview.start()

    # 4. 종료 후 잔존 프로세스 완전 강제 종료
    on_closed()


if __name__ == "__main__":
    main()
