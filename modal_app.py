"""Modal.com Serverless GPU Worker for ChannelDNA VOD Analysis & Subtitle Pipeline.

Deploys on NVIDIA L4 GPU with 2-minute turn-around for 6-hour broadcasts.
Exports both Solo XML and Collab XML alongside Smart Subtitles (SRT) and Guide (TXT).
"""

import gc
import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import modal

    app = modal.App("channel-dna-cloud")

    def download_models():
        from faster_whisper import WhisperModel
        from kiwipiepy import Kiwi
        print("[Build Time] Pre-downloading and baking Korean Whisper-Turbo into Docker image...")
        try:
            WhisperModel("deepdml/faster-whisper-large-v3-turbo-ct2", device="cpu", compute_type="int8")
        except Exception as e:
            print(f"[Build Warning] Falling back to standard large-v3-turbo: {e}")
            WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
        print("[Build Time] Pre-initializing Kiwi Korean morphological analyzer...")
        Kiwi(num_workers=1)
        print("[Build Time] All AI models baked successfully!")

    # Define high-speed Cloud container environment with FFmpeg & CUDA
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("ffmpeg", "git")
        .pip_install(
            "torch>=2.1.0",
            "torchaudio>=2.1.0",
            "nvidia-cublas-cu12",
            "nvidia-cudnn-cu12",
            "aiohttp>=3.9.0",
            "faster-whisper>=1.0.0",
            "kiwipiepy>=0.18.0",
            "librosa>=0.10.0",
            "soundfile>=0.12.1",
            "scipy>=1.11.0",
            "numba>=0.58.0",
            "requests>=2.31.0",
            "yt-dlp>=2024.1.0",
            "numpy>=1.24.0",
            "tqdm>=4.66.0",
        )
        .env(
            {
                "LD_LIBRARY_PATH": "/usr/local/lib/python3.11/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib:/usr/local/lib/python3.11/site-packages/nvidia/cuda_runtime/lib:$LD_LIBRARY_PATH",
                "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
            }
        )
        .run_function(download_models)
        .add_local_python_source("channel_dna")
    )
except ImportError:
    app = None
    image = None


@dataclass
class VodMetadata:
    video_no: str | None
    broadcast_date: str
    broadcast_title: str
    streamer_name: str


def _fetch_vod_metadata(vod_url_or_no: str, streamer_name: str) -> VodMetadata:
    """Extracts video ID and fetches metadata from Chzzk."""
    from channel_dna.core.chzzk_client import extract_chzzk_video_no, fetch_chzzk_video_meta

    broadcast_date = "20260825"
    broadcast_title = "치지직 다시보기"
    target_streamer = streamer_name.strip() if streamer_name else "스트리머"
    v_no = extract_chzzk_video_no(vod_url_or_no)

    if v_no:
        meta = fetch_chzzk_video_meta(v_no)
        if meta:
            if meta.get("date_str"):
                broadcast_date = meta["date_str"]
            if meta.get("title"):
                broadcast_title = meta["title"]
            if not streamer_name and meta.get("channel_name"):
                target_streamer = meta["channel_name"]

    return VodMetadata(
        video_no=v_no,
        broadcast_date=broadcast_date,
        broadcast_title=broadcast_title,
        streamer_name=target_streamer,
    )


def _resolve_streamer_profiles(
    facade: Any,
    target_streamer: str,
    solo_profile: dict[str, Any] | None,
    collab_profile: dict[str, Any] | None,
) -> tuple[Any, Any]:
    """Resolves Solo and Collab DNA Profiles dynamically from DB or overrides."""
    from channel_dna.core.models import (
        PSYCHOLOGY_COLLAB_PROFILE,
        PSYCHOLOGY_SOLO_PROFILE,
        ChannelProfile,
    )

    if solo_profile:
        solo_p = ChannelProfile.from_dict(solo_profile)
    else:
        db_solo = facade.db.get_profile(f"{target_streamer}_Solo") or facade.db.get_profile(target_streamer)
        if db_solo:
            solo_p = db_solo
        else:
            solo_p = ChannelProfile.from_dict(PSYCHOLOGY_SOLO_PROFILE)
            solo_p.channel_name = f"{target_streamer}_Solo"
    solo_p.profile_type = "solo"

    if collab_profile:
        collab_p = ChannelProfile.from_dict(collab_profile)
    else:
        db_collab = facade.db.get_profile(f"{target_streamer}_Collab")
        if db_collab:
            collab_p = db_collab
        else:
            collab_p = ChannelProfile.from_dict(PSYCHOLOGY_COLLAB_PROFILE)
            collab_p.channel_name = f"{target_streamer}_Collab"
    collab_p.profile_type = "collab"

    return solo_p, collab_p


def _execute_pipeline_core(
    vod_url_or_no: str,
    streamer_name: str = "",
    solo_profile: dict[str, Any] | None = None,
    collab_profile: dict[str, Any] | None = None,
    selected_mode: str = "solo",
) -> dict[str, Any]:
    """Core execution logic shared between Cloud Modal and Local Fallback."""
    from channel_dna.core.pipeline import PipelineFacade
    from channel_dna.core.utils import sanitize_filename

    facade = PipelineFacade()

    try:
        # [1/5] Metadata resolution
        meta = _fetch_vod_metadata(vod_url_or_no, streamer_name)
        target_streamer = meta.streamer_name
        broadcast_date = meta.broadcast_date
        broadcast_title = meta.broadcast_title
        v_no = meta.video_no

        print(
            f"[1/5] Starting VOD Pipeline for {vod_url_or_no} "
            f"(Target Streamer: {target_streamer}, Mode: {selected_mode})",
            flush=True,
        )
        print(f"[1/5] Metadata loaded: {broadcast_date} - {broadcast_title}", flush=True)

        # [2/5] Dynamic DNA Profiles
        solo_p, collab_p = _resolve_streamer_profiles(
            facade, target_streamer, solo_profile, collab_profile
        )

        # [2/5] Audio Extraction & Fast Chat Caching (Single Download)
        print("[2/5] Extracting audio stream once into memory (16kHz)...", flush=True)
        audio_samples = facade.scanner.audio_engine.extract_audio_in_memory(vod_url_or_no)
        facade.scanner.last_audio_samples = audio_samples

        total_dur_sec = len(audio_samples) / 16000.0 if len(audio_samples) > 0 else 0.0
        preloaded_chats = None
        if v_no and total_dur_sec > 0:
            try:
                print(f"[2/5] Fetching live chat logs for video {v_no} ({total_dur_sec:.1f}s)...", flush=True)
                preloaded_chats = facade.scanner.chat_engine.fetch_vod_chat_logs(v_no, total_dur_sec)
                print(f"[2/5] Chat logs loaded: {len(preloaded_chats) if preloaded_chats else 0} entries.", flush=True)
            except Exception as chat_err:
                print(f"[Chat Fetch Notice] {chat_err}", flush=True)

        solo_markers = []
        collab_markers = []

        if selected_mode in ("solo", "both"):
            print("[2/5] Scanning audio tension curves & DTW matching for Solo...", flush=True)
            solo_markers = facade.scanner.scan(
                vod_url_or_no,
                solo_p,
                scan_mode="solo",
                preloaded_audio=audio_samples,
                preloaded_chats=preloaded_chats,
            )
            print(f"[2/5] Solo scan complete: {len(solo_markers)} highlight markers identified.", flush=True)

        if selected_mode in ("collab", "both"):
            print("[2/5] Scanning audio tension curves & DTW matching for Collab...", flush=True)
            collab_markers = facade.scanner.scan(
                vod_url_or_no,
                collab_p,
                scan_mode="collab",
                preloaded_audio=audio_samples,
                preloaded_chats=preloaded_chats,
            )
            print(f"[2/5] Collab scan complete: {len(collab_markers)} highlight markers identified.", flush=True)

        # [3/5] Generate Subtitles for target markers
        target_markers = solo_markers if selected_mode == "solo" else (collab_markers if selected_mode == "collab" else solo_markers)
        target_p = solo_p if selected_mode == "solo" else (collab_p if selected_mode == "collab" else solo_p)

        subtitles = []
        if target_markers:
            try:
                print(
                    f"[3/5] Transcribing speech with Whisper AI on GPU & Kiwi alignment ({len(target_markers)} cuts)...",
                    flush=True,
                )
                subtitles = facade._generate_subtitles(
                    vod_url_or_no, broadcast_date, broadcast_title, target_markers, target_p, None
                )
                print(f"[3/5] Subtitle transcription complete: {len(subtitles)} dialogue segments.", flush=True)
            except Exception as e:
                print(f"[Subtitle STT Error] {e}", flush=True)

        # [4/5] Export XML to memory
        print("[4/5] Packaging Final Cut Pro XML & SRT subtitle files...", flush=True)
        clean_title = sanitize_filename(broadcast_title, max_length=40)
        clean_stem = f"{broadcast_date}_{clean_title}"
        tmp_dir = Path(tempfile.gettempdir())

        # Map subtitles to rough cut timeline
        solo_subs = None
        collab_subs = None
        target_subs = None

        if subtitles:
            if solo_markers:
                solo_subs = facade.subtitle_engine.map_subtitles_to_rough_cut(
                    subtitles, solo_markers, fps=60.0
                )
            if collab_markers:
                collab_subs = facade.subtitle_engine.map_subtitles_to_rough_cut(
                    subtitles, collab_markers, fps=60.0
                )
            target_subs = collab_subs if selected_mode == "collab" else solo_subs

        solo_xml_content = ""
        collab_xml_content = ""

        if solo_markers:
            solo_xml_path = tmp_dir / f"{clean_stem}_Solo_60fps.xml"
            facade.exporter.export(
                solo_markers,
                vod_url_or_no,
                str(solo_xml_path),
                fps=60.0,
                export_format="xml",
                video_file_name=f"{clean_stem}.mp4",
                subtitles=solo_subs,
                profile_type="solo",
            )
            solo_xml_content = solo_xml_path.read_text(encoding="utf-8") if solo_xml_path.exists() else ""

        if collab_markers:
            collab_xml_path = tmp_dir / f"{clean_stem}_Collab_60fps.xml"
            facade.exporter.export(
                collab_markers,
                vod_url_or_no,
                str(collab_xml_path),
                fps=60.0,
                export_format="xml",
                video_file_name=f"{clean_stem}.mp4",
                subtitles=collab_subs,
                profile_type="collab",
            )
            collab_xml_content = collab_xml_path.read_text(encoding="utf-8") if collab_xml_path.exists() else ""

        # [4/5] Export SRT to memory
        srt_content = ""
        if target_subs:
            srt_path = tmp_dir / f"{clean_stem}_자막.srt"
            facade.subtitle_engine.export_srt(target_subs, str(srt_path))
            srt_content = srt_path.read_text(encoding="utf-8") if srt_path.exists() else ""

        print("[5/5] Package successfully generated! Returning package to Discord bot.", flush=True)

        return {
            "success": True,
            "selected_mode": selected_mode,
            "streamer_name": target_streamer,
            "broadcast_title": broadcast_title,
            "broadcast_date": broadcast_date,
            "recommended_filename": f"{clean_stem}.mp4",
            "solo_xml_content": solo_xml_content,
            "collab_xml_content": collab_xml_content,
            "srt_content": srt_content,
            "solo_marker_count": len(solo_markers),
            "collab_marker_count": len(collab_markers),
            "sub_count": len(subtitles),
        }

    finally:
        # Explicit GPU memory and RAM cleanup
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        gc.collect()


def process_chzzk_vod_local(
    vod_url_or_no: str,
    streamer_name: str = "",
    solo_profile: dict[str, Any] | None = None,
    collab_profile: dict[str, Any] | None = None,
    selected_mode: str = "solo",
) -> dict[str, Any]:
    """Local fallback runner for development and offline execution."""
    return _execute_pipeline_core(
        vod_url_or_no, streamer_name, solo_profile, collab_profile, selected_mode
    )


if app is not None and image is not None:

    @app.function(
        image=image,
        gpu="L4",
        timeout=3600,
        cpu=4.0,
        memory=16384,
    )
    def process_chzzk_vod_cloud(
        vod_url_or_no: str,
        streamer_name: str = "",
        solo_profile: dict[str, Any] | None = None,
        collab_profile: dict[str, Any] | None = None,
        selected_mode: str = "solo",
    ) -> dict[str, Any]:
        """Serverless Cloud function executed on NVIDIA L4 GPU with dynamic DNA profile."""
        return _execute_pipeline_core(
            vod_url_or_no, streamer_name, solo_profile, collab_profile, selected_mode
        )

    @app.function(
        schedule=modal.Period(minutes=5),
        timeout=30,
    )
    def keep_render_bot_awake():
        """Periodically pings the Render Web Service every 5 minutes to prevent sleep."""
        import urllib.request

        try:
            req = urllib.request.Request(
                "https://roughcut-bot.onrender.com/health",
                headers={"User-Agent": "RoughCut-KeepAlive/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(f"[KeepAlive Ping] Render status: {resp.status}")
        except Exception as e:
            print(f"[KeepAlive Ping Notice] {e}")

    @app.local_entrypoint()
    def test_run(vod_no: str = "14728683", streamer: str = "양망두", mode: str = "solo"):
        print(f"Invoking process_chzzk_vod_cloud on Modal for {vod_no} ({streamer}, mode={mode})...")
        res = process_chzzk_vod_cloud.remote(vod_no, streamer, selected_mode=mode)
        print("Test Run Result:", res.get("success"), res.get("broadcast_title"))
