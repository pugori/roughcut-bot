import sys
import json
import argparse
from pathlib import Path

# Force UTF-8 for IO
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from channel_dna.core.service import ChannelDNAService

def emit(event_type: str, data: dict):
    line = json.dumps({"type": event_type, **data}, ensure_ascii=False)
    print(line, flush=True)

def handle_batch_extract(channel_url: str, streamer_name: str, count: int, sort_by: str):
    svc = ChannelDNAService()
    emit("progress", {"pct": 10, "msg": f"[{streamer_name}] yt-dlp 영상 탐색 시작..."})

    def progress_cb(stage: str, pct: float, msg: str):
        emit("progress", {"pct": int(pct * 100), "msg": f"[{stage}] {msg}"})

    def on_video_complete(idx: int, total: int, result):
        emit("video_complete", {
            "idx": idx,
            "total": total,
            "video_id": result.metadata.video_id,
            "title": result.metadata.title,
            "duration": result.metadata.duration,
            "asl": result.metadata.avg_shot_length,
            "video_type": getattr(result.metadata, "video_type", "solo")
        })

    def on_all_complete(total: int):
        solo_p, collab_p = svc.get_two_track_profiles(streamer_name)
        emit("all_complete", {
            "total": total,
            "solo_asl": solo_p.avg_shot_length if solo_p else 5.21,
            "collab_asl": collab_p.avg_shot_length if collab_p else 7.57
        })

    def on_error(err: Exception):
        emit("error", {"msg": str(err)})

    thread = svc.start_channel_batch_collection(
        channel_url=channel_url,
        channel_name=streamer_name,
        max_videos=count,
        sort_by="popular" if "인기" in sort_by else "balance",
        progress_cb=progress_cb,
        on_video_complete=on_video_complete,
        on_all_complete=on_all_complete,
        on_error=on_error
    )
    thread.join()

def handle_fetch_chzzk(channel_url_or_id: str):
    svc = ChannelDNAService()
    emit("progress", {"pct": 30, "msg": "치지직 VOD 목록 API 요청 중..."})
    try:
        vods = svc.fetch_chzzk_vod_catalog(channel_url_or_id, page_size=20)
        emit("chzzk_vods", {"vods": vods})
    except Exception as e:
        emit("error", {"msg": str(e)})

def handle_scan_vod(vod_url_or_no: str, streamer_name: str, dna_profile: str):
    import re
    import datetime
    import os
    import ctypes
    import cv2
    from pathlib import Path
    from channel_dna.core.utils import get_channel_marker_dir, build_vod_folder_and_filenames
    from channel_dna.core.guide_generator import GuideGenerator
    from channel_dna.core.service import ChannelDNAService
    from channel_dna.core.chzzk_client import fetch_chzzk_video_meta, extract_chzzk_video_no

    svc = ChannelDNAService()
    def progress_cb(stage: str, pct: float, msg: str):
        emit("progress", {"pct": int(pct * 100), "msg": f"[{stage}] {msg}"})

    def on_complete(markers, subtitles):
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        broadcast_date = today_str
        broadcast_title = Path(vod_url_or_no).stem if ("/" in vod_url_or_no or "\\" in vod_url_or_no) else ""

        # Fetch actual Chzzk broadcast date and broadcast title
        v_no = extract_chzzk_video_no(vod_url_or_no)
        if v_no:
            meta = fetch_chzzk_video_meta(v_no)
            if meta:
                if meta.get("date_str"):
                    broadcast_date = meta["date_str"]
                if meta.get("title"):
                    broadcast_title = meta["title"]

        if not broadcast_title:
            broadcast_title = f"VOD_{vod_url_or_no}"

        # If local file stem starts with 8-digit date, extract date and title
        m_date = re.match(r"^(\d{8})[_\s](.+)$", broadcast_title)
        if m_date:
            broadcast_date = m_date.group(1)
            broadcast_title = m_date.group(2)

        folder_name, xml_name, _edl_name, srt_name = build_vod_folder_and_filenames(broadcast_date, broadcast_title)
        
        base_dir = get_channel_marker_dir(streamer_name)
        pkg_dir = base_dir / folder_name
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # Detect actual video FPS dynamically (e.g. 30.0fps or 60.0fps)
        actual_fps = 60.0
        if not (vod_url_or_no.startswith("http://") or vod_url_or_no.startswith("https://")):
            check_path = os.path.abspath(vod_url_or_no)
            if os.name == "nt" and os.path.exists(check_path):
                try:
                    buf = ctypes.create_unicode_buffer(1024)
                    if ctypes.windll.kernel32.GetShortPathNameW(check_path, buf, 1024) > 0:
                        check_path = buf.value
                except Exception:
                    pass
            try:
                cap = cv2.VideoCapture(check_path)
                if cap.isOpened():
                    f_val = cap.get(cv2.CAP_PROP_FPS)
                    if f_val and f_val > 0:
                        actual_fps = float(f_val)
                    cap.release()
            except Exception:
                pass

        # 1. Master XML (Auto-matched Native FPS: Premiere Pro & DaVinci Resolve 100% Compatible)
        if markers:
            svc._facade.exporter.export(markers, vod_url_or_no, str(pkg_dir / xml_name), fps=actual_fps, export_format="xml")
        
        # 2. Universal Subtitles (.srt)
        if subtitles:
            rough_subs = svc._facade.subtitle_engine.map_subtitles_to_rough_cut(subtitles, markers, fps=actual_fps)
            if rough_subs:
                svc._facade.subtitle_engine.export_srt(rough_subs, str(pkg_dir / srt_name))
        
        # 3. Studio Guide Notice (.txt)
        GuideGenerator.save_guide_to_package(
            package_dir=pkg_dir,
            vod_title=broadcast_title,
            vod_date=broadcast_date,
            total_markers=len(markers)
        )

        emit("scan_complete", {
            "markers_count": len(markers),
            "subtitles_count": len(subtitles),
            "package_folder": str(pkg_dir),
            "fps": actual_fps
        })

    def on_error(err: Exception):
        emit("error", {"msg": str(err)})

    thread = svc.start_vod_timeline_scan(
        vod_url_or_no=vod_url_or_no,
        channel_name=streamer_name,
        dna_profile_name=dna_profile,
        progress_cb=progress_cb,
        on_complete=on_complete,
        on_error=on_error
    )
    thread.join()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    p_extract = sub.add_parser("batch_extract")
    p_extract.add_argument("--url", required=True)
    p_extract.add_argument("--streamer", required=True)
    p_extract.add_argument("--count", type=int, default=5)
    p_extract.add_argument("--sort", default="balance")

    p_chzzk = sub.add_parser("fetch_chzzk")
    p_chzzk.add_argument("--target", required=True)

    p_scan = sub.add_parser("scan_vod")
    p_scan.add_argument("--vod", required=True)
    p_scan.add_argument("--streamer", required=True)
    p_scan.add_argument("--dna", required=True)

    args = parser.parse_args()
    if args.cmd == "batch_extract":
        handle_batch_extract(args.url, args.streamer, args.count, args.sort)
    elif args.cmd == "fetch_chzzk":
        handle_fetch_chzzk(args.target)
    elif args.cmd == "scan_vod":
        handle_scan_vod(args.vod, args.streamer, args.dna)
    else:
        print("Unknown command")




