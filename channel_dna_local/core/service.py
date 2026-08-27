"""ChannelDNA Unified Internal Service API Gateway (Clean Architecture Contract).

This service acts as the SINGLE decoupled interface between the presentation/GUI layer 
and the core domain engines (DB, Profiler, Extractor, Scanner, Chzzk, RiskEngine).
"""

from __future__ import annotations
import dataclasses
import json
import threading
from pathlib import Path
from typing import Any, Callable

from channel_dna_local.core.chzzk_client import fetch_chzzk_vod_list
from channel_dna_local.core.classifier import classify_youtube_video
from channel_dna_local.core.db import DBManager
from channel_dna_local.core.logger import get_logger
from channel_dna_local.core.models import ChannelProfile, ScanMarker, SubtitleItem, VideoAnalysisResult, VideoMetadata
from channel_dna_local.core.pipeline import PipelineFacade
from channel_dna_local.core.utils import (
    build_vod_folder_and_filenames,
    get_channel_marker_dir,
)

_logger = get_logger(__name__)


class ChannelDNAService:
    """The central decoupled API Service for all ChannelDNA operations."""

    def __init__(self, db_path: str | Path | None = None):
        self._facade = PipelineFacade(db_path=str(db_path) if db_path else None)
        self._db: DBManager = self._facade.db

    # =========================================================================
    # 1. System & Catalog Query APIs
    # =========================================================================

    def get_system_stats(self) -> dict[str, Any]:
        """Returns overall database statistics (channel count, total videos)."""
        return self._db.get_db_stats()

    def get_registered_streamers(self) -> list[str]:
        """Returns a list of distinct streamer names stored in the database."""
        raw_names = self._db.get_channel_names()
        return sorted(
            list(
                set(
                    n.replace("_Solo", "").replace("_Collab", "")
                    for n in raw_names
                    if n and not n.startswith("🤖")
                )
            )
        )

    def get_video_catalog(self) -> list[VideoMetadata]:
        """Returns all collected YouTube/local videos with metadata."""
        return self._db.get_all_videos()

    def get_video_segments_count(self, video_id: str) -> int:
        """Returns the number of cuts/segments analyzed for a specific video."""
        segs = self._db.get_segments_by_video(video_id)
        return len(segs) if segs else 0

    # =========================================================================
    # 2. DNA Profile Management APIs
    # =========================================================================

    def get_two_track_profiles(self, streamer_name: str) -> tuple[ChannelProfile | None, ChannelProfile | None]:
        """Retrieves (Solo, Collab) profiles for a given streamer."""
        if not streamer_name or streamer_name.startswith("("):
            return None, None
        p_solo = self._db.get_profile(f"{streamer_name}_Solo") or self._db.get_profile(streamer_name)
        p_collab = self._db.get_profile(f"{streamer_name}_Collab")
        return p_solo, p_collab

    def recalculate_streamer_dna(self, streamer_name: str) -> tuple[ChannelProfile, ChannelProfile]:
        """Recalculates and updates Two-Track DNA profiles from collected videos."""
        return self._facade.derive_two_track_profiles(streamer_name)

    def save_manual_profile(self, profile: ChannelProfile) -> bool:
        """Persists a manually tuned ChannelProfile into SQLite DB."""
        try:
            self._db.save_profile(profile)
            return True
        except Exception as e:
            _logger.error("Failed to save manual profile: %s", e)
            return False

    def update_streamer_urls(self, streamer_name: str, youtube_url: str | None = None, chzzk_url: str | None = None):
        """Updates or registers YouTube and Chzzk channel URLs for a streamer."""
        self._db.update_channel_urls(channel_name=streamer_name, youtube_url=youtube_url, chzzk_url=chzzk_url)

    def get_streamer_channel_urls(self, streamer_name: str) -> tuple[str, str]:
        """Returns (youtube_url, chzzk_url) registered for a streamer."""
        p = self._db.get_profile(f"{streamer_name}_Solo") or self._db.get_profile(streamer_name)
        if p:
            return getattr(p, "youtube_url", "") or "", getattr(p, "chzzk_url", "") or ""
        return "", ""

    # =========================================================================
    # 3. Video Classification & Quick Toggle APIs
    # =========================================================================

    def ensure_video_classification(self, video: VideoMetadata) -> str:
        """Ensures a video has a valid 'solo' or 'collab' classification in DB (fast 0.01s heuristic)."""
        cur_type = getattr(video, "video_type", "auto")
        if cur_type in ("solo", "collab"):
            return cur_type

        # Run fast heuristic without blocking LLM
        segs = self._db.get_segments_by_video(video.video_id)
        try:
            res = classify_youtube_video(
                video.title,
                avg_shot_length=video.avg_shot_length,
                duration=video.duration,
                segments=segs,
                use_llm=False,
            )
        except TypeError:
            res = classify_youtube_video(
                video.title,
                avg_shot_length=video.avg_shot_length,
                duration=video.duration,
                segments=segs,
            )
        v_type = res[0] if isinstance(res, tuple) else res
        self._db.update_video_type(video.video_id, v_type)
        return v_type

    def toggle_video_classification(self, video_id: str) -> tuple[str, str, str]:
        """Toggles video type (solo <-> collab), updates DB, and re-derives DNA.
        
        Returns: (video_title, old_type, new_type)
        """
        v = self._db.get_video_by_id(video_id)
        if not v:
            return "", "", ""
        old_type = getattr(v, "video_type", "solo")
        new_type = "collab" if old_type == "solo" else "solo"
        ch = v.channel_name or ""
        self._facade.update_video_type_and_reprofile(video_id, ch, new_type)
        return v.title or "", old_type, new_type

    # =========================================================================
    # 4. Asynchronous Task Operations (Background Workers)
    # =========================================================================

    def start_channel_batch_collection(
        self,
        channel_url: str,
        channel_name: str,
        max_videos: int = 5,
        sort_by: str = "balance",
        progress_cb: Callable[[str, float, str], None] | None = None,
        on_video_complete: Callable[[int, int, VideoAnalysisResult], None] | None = None,
        on_all_complete: Callable[[int], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> threading.Thread:
        """Starts batch downloading, cut extraction, tension modeling and DNA learning."""
        return self._facade.run_batch_extraction_worker(
            channel_url=channel_url,
            channel_name=channel_name,
            max_videos=max_videos,
            sort_by=sort_by,
            progress_cb=progress_cb,
            on_video_complete=on_video_complete,
            on_all_complete=on_all_complete,
            on_error=on_error,
        )

    def start_single_video_extraction(
        self,
        source: str,
        channel_name: str,
        progress_cb: Callable[[str, float, str], None] | None = None,
        on_complete: Callable[[VideoAnalysisResult], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> threading.Thread:
        """Starts extraction on a single YouTube URL or local video file."""
        return self._facade.run_extraction_worker(
            video_input=source,
            channel_name=channel_name,
            is_url=source.startswith("http"),
            progress_cb=progress_cb,
            on_complete=on_complete,
            on_error=on_error,
        )

    def fetch_chzzk_vod_catalog(self, channel_url_or_id: str, page_size: int = 40) -> list[dict[str, Any]]:
        """Synchronously fetches past VODs from Chzzk API."""
        return fetch_chzzk_vod_list(channel_url_or_id, page_size=page_size)

    def start_vod_timeline_scan(
        self,
        vod_url_or_no: str,
        channel_name: str,
        dna_profile_name: str,
        progress_cb: Callable[[str, float, str], None] | None = None,
        on_complete: Callable[[list[ScanMarker], list[SubtitleItem]], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        vod_title: str | None = None,
        vod_date: str | None = None,
    ) -> threading.Thread:
        """Starts full VOD timeline scanning with DNA profile match and export."""
        return self._facade.run_scan_worker(
            vod_path=vod_url_or_no,
            channel_name=channel_name,
            dna_profile_name=dna_profile_name,
            progress_cb=progress_cb,
            on_complete=on_complete,
            on_error=on_error,
            vod_title=vod_title,
            vod_date=vod_date,
        )

    def export_nle_packages(
        self,
        vod_title: str,
        vod_date: str,
        markers: list[ScanMarker],
        subtitles: list[SubtitleItem],
        output_dir: str,
        fps: float = 60.0,
    ) -> dict[str, str]:
        """Exports FCP7 XML, DaVinci EDL, and SRT packages."""
        return self._facade.export_streamer_package(
            vod_title=vod_title,
            vod_date=vod_date,
            markers=markers,
            subtitles=subtitles,
            output_dir=output_dir,
            fps=fps,
        )

