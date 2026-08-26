"""High-level Pipeline Facade for ChannelDNA operations with Ultra-Fast Lazy Initialization."""

from channel_dna.core.logger import get_logger

_logger = get_logger(__name__)

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from channel_dna.core.db import DBManager
from channel_dna.core.models import (
    ChannelProfile,
    ProgressCallback,
    ScanMarker,
    VideoAnalysisResult,
)
from channel_dna.core.subtitle_formatter import SubtitleItem


def _launch_worker(worker_func: Callable) -> threading.Thread:
    thread = threading.Thread(target=worker_func, daemon=True)
    thread.start()
    return thread


class PipelineFacade:
    def __init__(self, db_path: str | None = None):
        self.db = DBManager(db_path)
        self._audio_engine = None
        self._extractor = None
        self._profiler = None
        self._scanner = None
        self._exporter = None
        self._subtitle_engine = None
        self._issue_collector = None
        self._risk_engine = None
        self._report_generator = None
        self._rough_cut_renderer = None
        self._guide_generator = None
        self._llm_engine = None

    @property
    def audio_engine(self):
        if self._audio_engine is None:
            from channel_dna.core.audio_engine import AudioEngine

            self._audio_engine = AudioEngine()
        return self._audio_engine

    @property
    def extractor(self):
        if self._extractor is None:
            from channel_dna.core.extractor import VideoExtractor

            self._extractor = VideoExtractor(self.audio_engine)
        return self._extractor

    @property
    def profiler(self):
        if self._profiler is None:
            from channel_dna.core.profiler import ChannelProfiler

            self._profiler = ChannelProfiler(self.db)
        return self._profiler

    @property
    def scanner(self):
        if self._scanner is None:
            from channel_dna.core.scanner import VODScanner

            self._scanner = VODScanner(self.audio_engine)
        return self._scanner

    @property
    def graph_engine(self):
        return self.scanner.graph_engine

    @property
    def exporter(self):
        if self._exporter is None:
            from channel_dna.core.exporter import MarkerExporter

            self._exporter = MarkerExporter()
        return self._exporter

    @property
    def subtitle_engine(self):
        if self._subtitle_engine is None:
            from channel_dna.core.subtitles import SubtitleEngine

            self._subtitle_engine = SubtitleEngine()
        return self._subtitle_engine

    @property
    def issue_collector(self):
        if self._issue_collector is None:
            from channel_dna.core.risk_engine import IssueDBCollector

            self._issue_collector = IssueDBCollector(self.db.db_path)
        return self._issue_collector

    @property
    def risk_engine(self):
        if self._risk_engine is None:
            from channel_dna.core.risk_engine import RiskEngine

            self._risk_engine = RiskEngine(self.issue_collector)
        return self._risk_engine

    @property
    def report_generator(self):
        if self._report_generator is None:
            from channel_dna.core.report_generator import ReportGenerator

            self._report_generator = ReportGenerator()
        return self._report_generator

    @property
    def rough_cut_renderer(self):
        if self._rough_cut_renderer is None:
            from channel_dna.core.rough_cut_renderer import RoughCutRenderer

            self._rough_cut_renderer = RoughCutRenderer()
        return self._rough_cut_renderer

    @property
    def guide_generator(self):
        if self._guide_generator is None:
            from channel_dna.core.guide_generator import GuideGenerator

            self._guide_generator = GuideGenerator()
        return self._guide_generator

    @property
    def llm_engine(self):
        if self._llm_engine is None:
            from channel_dna.core.llm_engine import LocalLLMEngine

            self._llm_engine = LocalLLMEngine()
        return self._llm_engine

    def update_video_type_and_reprofile(
        self, video_id: str, channel_name: str, new_type: str
    ) -> tuple[ChannelProfile, ChannelProfile]:
        """Manually update video classification (solo/collab) in DB and re-derive Two-Track profiles in 0.01s."""
        return self.profiler.update_video_type_and_reprofile(
            video_id, channel_name, new_type
        )

    def clear_cache(self, older_than_days: int | None = None) -> int:
        """Clear cached VOD audio tensions and chat JSONs from .cache dir."""
        import time

        from channel_dna.config import config

        cache_dir = config.default_cache_dir
        if not cache_dir.exists():
            return 0

        deleted = 0
        now = time.time()
        max_age_sec = (older_than_days * 86400) if older_than_days else 0

        for f in cache_dir.glob("*"):
            if f.is_file() and (f.suffix in (".npz", ".json", ".wav", ".mp3")):
                if max_age_sec == 0 or (now - f.stat().st_mtime) > max_age_sec:
                    try:
                        f.unlink()
                        deleted += 1
                    except Exception as e:
                        _logger.debug("Silenced exception: %s", e)
        return deleted

    def run_issue_collection_worker(
        self,
        progress_cb: ProgressCallback | None = None,
        on_complete: Callable[[int], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> threading.Thread:
        """Run free community & wiki issue keyword collection (0 API cost, manual trigger)."""

        def _worker():
            try:
                count = self.issue_collector.collect_from_web(progress_cb=progress_cb)
                if on_complete:
                    on_complete(count)
            except Exception as e:
                if on_error:
                    on_error(e)

        return _launch_worker(_worker)

    def run_scan_worker(
        self,
        vod_path: str,
        channel_name: str,
        dna_profile_name: str | None = None,
        use_cache: bool = True,
        generate_subtitles: bool = True,
        scan_mode: str = "dna_solo",
        progress_cb: ProgressCallback | None = None,
        on_complete: Callable[[list[ScanMarker], list[SubtitleItem]], None]
        | None = None,
        on_error: Callable[[Exception], None] | None = None,
        cancel_event: threading.Event | None = None,
        expected_duration_sec: float | None = None,
        vod_title: str | None = None,
        vod_date: str | None = None,
    ) -> threading.Thread:
        """Run raw VOD scanning with chosen DNA profile + pinpoint subtitle generation for highlight slices."""

        def _worker():
            try:
                from channel_dna.core.models import (
                    PSYCHOLOGY_COLLAB_PROFILE,
                    PSYCHOLOGY_SOLO_PROFILE,
                )

                prof_target = dna_profile_name or channel_name
                streamer_profile = self.db.get_profile(prof_target)
                if not streamer_profile:
                    streamer_profile = self.profiler.derive_profile(prof_target)

                # Route requested weighting mode
                clean_scan_mode = scan_mode.lower()
                if "psychology_solo" in clean_scan_mode:
                    import copy

                    profile = copy.deepcopy(PSYCHOLOGY_SOLO_PROFILE)
                    if streamer_profile and streamer_profile.custom_vocab:
                        profile.custom_vocab = streamer_profile.custom_vocab
                    target_scan_mode = "solo"
                elif "psychology_collab" in clean_scan_mode:
                    import copy

                    profile = copy.deepcopy(PSYCHOLOGY_COLLAB_PROFILE)
                    if streamer_profile and streamer_profile.custom_vocab:
                        profile.custom_vocab = streamer_profile.custom_vocab
                        profile.host_voice_print = streamer_profile.host_voice_print
                    target_scan_mode = "collab"
                elif "dna_collab" in clean_scan_mode or clean_scan_mode == "collab":
                    base_ch = prof_target.replace("_Solo", "").replace("_Collab", "")
                    collab_p = self.db.get_profile(f"{base_ch}_Collab")
                    profile = collab_p or streamer_profile
                    if profile:
                        profile.profile_type = "collab"
                    target_scan_mode = "collab"
                else:
                    base_ch = prof_target.replace("_Solo", "").replace("_Collab", "")
                    solo_p = self.db.get_profile(f"{base_ch}_Solo")
                    profile = solo_p or streamer_profile
                    if profile:
                        profile.profile_type = "solo"
                    target_scan_mode = "solo"

                markers = self.scanner.scan(
                    vod_path,
                    profile,
                    use_cache=use_cache,
                    scan_mode=target_scan_mode,
                    progress_cb=progress_cb,
                    cancel_event=cancel_event,
                    expected_duration_sec=expected_duration_sec,
                )

                subtitles: list[SubtitleItem] = []
                if generate_subtitles and markers:
                    try:
                        subtitles = self._generate_subtitles(
                            vod_path, vod_date, vod_title, markers, profile, progress_cb
                        )
                    except Exception as sub_err:
                        print(f"[Subtitle Pipeline Error] {sub_err}")
                        if progress_cb:
                            progress_cb("Warning", 0.95, f"자막 생성 참고: {sub_err}")

                # Export is now decoupled. Just clean up memory.
                import gc

                gc.collect()

                if progress_cb:
                    progress_cb(
                        "Complete",
                        1.0,
                        f"✓ 분석 완료 (마커 {len(markers)}개, 자막 {len(subtitles)}개)",
                    )

                if on_complete:
                    on_complete(markers, subtitles)
            except Exception as e:
                if on_error:
                    on_error(e)

        return _launch_worker(_worker)

    def _generate_subtitles(
        self,
        vod_path: str,
        vod_date: str | None,
        vod_title: str | None,
        markers: list[ScanMarker],
        profile: ChannelProfile,
        progress_cb: ProgressCallback | None,
    ) -> list[SubtitleItem]:
        if progress_cb:
            progress_cb(
                "SubtitleGen",
                0.88,
                f"채널 사전 기반 초벌 자막 생성 시작 (총 {len(markers)}개 하이라이트 구간)...",
            )

        import os

        user_downloads = Path(os.path.expanduser("~")) / "Downloads"
        local_matches = list(user_downloads.glob("*.mp4")) + list(
            Path(".").glob("*.mp4")
        )
        local_src = vod_path
        for candidate in local_matches:
            cand_stem = candidate.stem
            if (vod_date and vod_date in cand_stem) or (
                vod_title
                and any(w in cand_stem for w in vod_title.split()[:2] if len(w) > 2)
            ):
                local_src = str(candidate)
                break

        audio_data = getattr(self.scanner, "last_audio_samples", None)

        # Phase 2: Dynamic RAG Vocabulary
        dynamic_vocab = ""
        if vod_title:
            if progress_cb:
                progress_cb(
                    "SubtitleGen",
                    0.88,
                    "초경량 AI 자막 엔진 및 동적 게임 사전 로드 중...",
                )
            # Use top 200 chars of chat as context if available
            chat_hist = getattr(self.scanner, "chat_history", [])
            chat_ctx = " ".join([c["msg"] for c in chat_hist[:30]]) if chat_hist else ""
            dynamic_vocab = self.llm_engine.extract_dynamic_vocabulary(
                vod_title, chat_ctx
            )
            if dynamic_vocab:
                print(f"[Dynamic RAG] 추가된 고유명사: {dynamic_vocab}")

        combined_vocab = profile.custom_vocab
        if dynamic_vocab:
            combined_vocab = (
                f"{profile.custom_vocab}, {dynamic_vocab}"
                if profile.custom_vocab
                else dynamic_vocab
            )

        return self.subtitle_engine.generate_subtitles_for_markers(
            audio_data=audio_data,
            markers=markers,
            custom_vocab_prompt=combined_vocab,
            progress_cb=progress_cb,
            source_path=local_src,
            profile=profile,
        )

    def run_export_files(
        self,
        vod_path: str,
        channel_name: str,
        vod_date: str,
        vod_title: str,
        markers: list[ScanMarker],
        subtitles: list[SubtitleItem],
        progress_cb: ProgressCallback | None = None,
        on_complete: Callable[[Path], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ):
        def _worker():
            try:
                if progress_cb:
                    progress_cb(
                        "Export",
                        0.1,
                        "스트리머 납품용 표준 패키지(XML, EDL, SRT) 파일 생성 중...",
                    )
                import datetime

                from channel_dna.core.utils import (
                    build_vod_folder_and_filenames,
                    get_channel_marker_dir,
                )

                today_str = vod_date or datetime.datetime.now().strftime("%Y%m%d")
                stem_title = vod_title or Path(vod_path).stem
                folder_name, xml_name, edl_name, srt_name = (
                    build_vod_folder_and_filenames(today_str, stem_title)
                )

                base_out_dir = get_channel_marker_dir(channel_name)
                pkg_dir = base_out_dir / folder_name
                pkg_dir.mkdir(parents=True, exist_ok=True)

                # Get actual FPS natively from the Stream or File
                _ = 60.0
                if progress_cb:
                    progress_cb("Export", 0.4, "프레임 레이트 감지 중...")
                if "http" in vod_path:
                    try:
                        import yt_dlp

                        ydl_opts = {
                            "quiet": True,
                            "no_warnings": True,
                            "extract_flat": False,
                        }
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(vod_path, download=False)
                            if info and info.get("fps"):
                                _ = float(info["fps"])
                    except Exception as e:
                        _logger.debug("Silenced exception: %s", e)
                else:
                    try:
                        import cv2

                        cap = cv2.VideoCapture(vod_path)
                        if cap.isOpened():
                            fps_val = cap.get(cv2.CAP_PROP_FPS)
                            if fps_val > 0:
                                _ = fps_val
                            cap.release()
                    except Exception as e:
                        _logger.debug("Silenced exception: %s", e)

                p_type = getattr(profile, "profile_type", "solo") or "solo"
                rough_subs = None
                if subtitles:
                    if progress_cb:
                        progress_cb("Export", 0.70, "공용 초벌 자막 및 타임라인 동기화 중...")
                    rough_subs = self.subtitle_engine.map_subtitles_to_rough_cut(
                        subtitles, markers, fps=60.0
                    )
                    if rough_subs:
                        self.subtitle_engine.export_srt(
                            rough_subs, str(pkg_dir / srt_name)
                        )

                if progress_cb:
                    progress_cb(
                        "Export",
                        0.80,
                        "통합 타임라인(XML: V1~V4 트랙) 및 공용 초벌 자막(SRT) 생성 중...",
                    )

                # 1. 60fps Master XML (메인 공용 가편집본: [날짜+제목].xml, 화자별 자막 트랙 포함)
                self.exporter.export(
                    markers,
                    vod_path,
                    str(pkg_dir / xml_name),
                    fps=60.0,
                    export_format="xml",
                    video_file_name=f"{folder_name}.mp4",
                    subtitles=rough_subs,
                    profile_type=p_type,
                )

                # 2. Universal OpenTimelineIO (.otio: [날짜+제목].otio)
                otio_name = f"{folder_name}.otio"
                self.exporter.export(
                    markers,
                    vod_path,
                    str(pkg_dir / otio_name),
                    fps=60.0,
                    export_format="otio",
                    video_file_name=f"{folder_name}.mp4",
                )

                # 3. 30fps Test XML (개발자 테스트용: [날짜+제목]_30fps.xml)
                xml_30_name = xml_name.replace(".xml", "_30fps.xml")
                self.exporter.export(
                    markers,
                    vod_path,
                    str(pkg_dir / xml_30_name),
                    fps=30.0,
                    export_format="xml",
                    video_file_name=f"{folder_name}.mp4",
                    subtitles=rough_subs,
                    profile_type=p_type,
                )


                # Generate clean studio notice & usage guide document
                if progress_cb:
                    progress_cb("Export", 0.95, "안내 및 활용 가이드 문서 작성 중...")
                self.guide_generator.save_guide_to_package(
                    package_dir=pkg_dir,
                    vod_title=vod_title or folder_name,
                    vod_date=vod_date or "",
                    total_markers=len(markers),
                )

                if progress_cb:
                    progress_cb(
                        "Complete", 1.0, f"표준 편집 패키지 생성 완료: {pkg_dir.name}"
                    )
                if on_complete:
                    on_complete(pkg_dir)
            except Exception as e:
                if on_error:
                    on_error(e)

        return _launch_worker(_worker)

    def run_rough_cut_video_worker(
        self,
        vod_path: str,
        markers: list[ScanMarker],
        output_mp4_path: str,
        progress_cb: ProgressCallback | None = None,
        on_complete: Callable[[Path], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> threading.Thread:
        """Renders full rough cut MP4 video by concatenating all scan markers in background."""

        def _worker():
            try:
                out_p = self.rough_cut_renderer.render_full_rough_cut(
                    vod_path=vod_path,
                    markers=markers,
                    output_mp4_path=output_mp4_path,
                    progress_cb=progress_cb,
                    cancel_event=cancel_event,
                )
                if on_complete:
                    on_complete(out_p)
            except Exception as e:
                if on_error:
                    on_error(e)

        return _launch_worker(_worker)

    def inspect_issues_and_generate_reports(
        self,
        vod_title: str,
        vod_date: str,
        vod_duration_sec: float,
        markers: list[ScanMarker],
        subtitles: list[SubtitleItem],
        base_output_path: str,
    ) -> tuple[Path, Path, list[Any]]:
        """Scans subtitles for issue keywords and generates pure fact-based MD & TXT reports."""
        issue_matches = (
            self.risk_engine.inspect_subtitles(subtitles) if subtitles else []
        )
        p = Path(base_output_path)
        stem = (
            p.stem.replace("_markers", "")
            .replace("_davinci", "")
            .replace("_premiere", "")
        )
        parent = p.parent

        md_path = parent / f"{stem}_qa_context_report.md"
        txt_path = parent / f"{stem}_qa_context_report.txt"

        self.report_generator.generate_markdown_report(
            vod_title=vod_title,
            vod_date=vod_date,
            vod_duration_sec=vod_duration_sec,
            markers=markers,
            issue_matches=issue_matches,
            output_path=str(md_path),
        )

        self.report_generator.generate_text_report(
            vod_title=vod_title,
            vod_date=vod_date,
            vod_duration_sec=vod_duration_sec,
            markers=markers,
            issue_matches=issue_matches,
            output_path=str(txt_path),
        )

        return md_path, txt_path, issue_matches

    def run_extraction_worker(
        self,
        video_input: str,
        channel_name: str | None,
        is_url: bool,
        progress_cb: ProgressCallback | None = None,
        on_complete: Callable[[VideoAnalysisResult], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> threading.Thread:
        def _worker():
            try:
                result = self.extractor.analyze(
                    video_input, channel_name, is_url, progress_cb
                )
                self.db.save_video_analysis(result.metadata, result.segments)
                if on_complete:
                    on_complete(result)
            except Exception as e:
                if on_error:
                    on_error(e)

        return _launch_worker(_worker)

    def run_batch_extraction_worker(
        self,
        channel_url: str,
        channel_name: str,
        max_videos: int = 5,
        sort_by: str = "popular",
        progress_cb: ProgressCallback | None = None,
        on_video_complete: Callable[[int, int, VideoAnalysisResult], None]
        | None = None,
        on_all_complete: Callable[[int], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> threading.Thread:
        def _worker():
            try:
                import urllib.parse

                clean_channel_url = urllib.parse.unquote(channel_url.strip())
                clean_channel_name = (
                    urllib.parse.unquote(channel_name.strip())
                    if channel_name
                    else "YouTube_Channel"
                )

                if sort_by == "balance":
                    sort_name = "밸런스(인기+최신 통합)"
                    if progress_cb:
                        progress_cb(
                            "ChannelScan",
                            0.05,
                            f"유튜브 채널 인기/최신 영상 목록 동시 탐색 중: {clean_channel_url}",
                        )
                    pop_vids = self.extractor.fetch_channel_videos(
                        clean_channel_url, max_videos, sort_by="popular"
                    )
                    lat_vids = self.extractor.fetch_channel_videos(
                        clean_channel_url, max_videos, sort_by="latest"
                    )

                    # Merge and Deduplicate by video ID
                    merged = {}
                    for v in pop_vids + lat_vids:
                        merged[v.get("id") or v["url"]] = v
                    videos = list(merged.values())
                else:
                    sort_name = (
                        "인기순(조회수 최고)" if sort_by == "popular" else "최신순"
                    )
                    if progress_cb:
                        progress_cb(
                            "ChannelScan",
                            0.05,
                            f"유튜브 채널 {sort_name} 영상 목록 탐색 중: {clean_channel_url}",
                        )
                    videos = self.extractor.fetch_channel_videos(
                        clean_channel_url,
                        max_videos,
                        sort_by=sort_by,
                        progress_cb=progress_cb,
                    )

                if not videos:
                    raise ValueError(
                        f"채널에서 영상을 찾을 수 없습니다: {clean_channel_url}"
                    )

                total = len(videos)
                saved_count = 0
                skipped_count = 0

                for idx, v in enumerate(videos, 1):
                    v_id = v.get("id")
                    v_url = v["url"]
                    v_title = v["title"]

                    def item_progress(stage: str, pct: float, msg: str):
                        overall_pct = ((idx - 1) + pct) / total
                        if progress_cb:
                            progress_cb(stage, overall_pct, f"[{idx}/{total}편] {msg}")

                    try:
                        # [정밀 데이터 완전성 검사] 이미 완전 분석된 영상만 스킵, 필수 피처 누락 시 자동 보강 분석
                        is_complete = False
                        with self.db._get_connection() as conn:
                            if v_id:
                                is_complete = self.db.is_video_analysis_complete(conn, v_id)

                        if is_complete:
                            skipped_count += 1
                            if progress_cb:
                                progress_cb(
                                    "Skip",
                                    idx / total,
                                    f"[{idx}/{total}편 건너뜀] 이미 완전 분석된 영상입니다: {v_title}",
                                )
                            continue

                        result = self.extractor.analyze(
                            v_url, clean_channel_name, is_url=True, progress_cb=item_progress
                        )
                        self.db.save_video_analysis(result.metadata, result.segments)
                        saved_count += 1
                        if on_video_complete:
                            on_video_complete(idx, total, result)
                    except Exception as item_err:
                        if progress_cb:
                            progress_cb(
                                "Warning",
                                idx / total,
                                f"[{idx}/{total}편 오류] {v_title}: {item_err}",
                            )

                if saved_count > 0 or skipped_count > 0:
                    try:
                        self.profiler.derive_two_track_profiles(clean_channel_name)
                    except Exception as prof_err:
                        print(f"Two-Track Profile Auto-Derivation Note: {prof_err}")

                if on_all_complete:
                    on_all_complete(saved_count + skipped_count)

            except Exception as e:
                if on_error:
                    on_error(e)

        return _launch_worker(_worker)

    def export_streamer_package(
        self,
        vod_title: str,
        vod_date: str,
        markers: list[ScanMarker],
        subtitles: list[SubtitleItem],
        output_dir: str,
        fps: float = 60.0,
    ) -> dict[str, str]:
        """Exports clean multi-NLE package inside [date_title] subfolder for Google Drive organization.
        Generates strictly:
        - [date_title]/[date_title]_premiere_markers.xml
        - [date_title]/[date_title]_davinci_markers.edl
        - [date_title]/[date_title]_subtitles.srt
        """
        from channel_dna.core.utils import build_vod_folder_and_filenames

        folder_name, xml_name, edl_name, srt_name = build_vod_folder_and_filenames(
            vod_date, vod_title
        )

        vod_subfolder = Path(output_dir) / folder_name
        vod_subfolder.mkdir(parents=True, exist_ok=True)

        xml_path = vod_subfolder / xml_name
        edl_path = vod_subfolder / edl_name
        srt_path = vod_subfolder / srt_name

        # 1. Export Markers (Official XML for Premiere Pro, EDL for DaVinci Resolve)
        if markers:
            rough_subs = None
            if subtitles:
                rough_subs = self.subtitle_engine.map_subtitles_to_rough_cut(
                    subtitles, markers, fps=fps
                )
            self.exporter.xml_exp.export(
                markers, vod_title, str(xml_path), fps=fps, subtitles=rough_subs
            )
            self.exporter.edl_exp.export(markers, vod_title, str(edl_path), fps=fps)

        # 2. Export Subtitles (SRT with absolute VOD timecodes)
        if subtitles:
            self.subtitle_engine.export_srt(subtitles, str(srt_path))

        return {
            "premiere_xml": str(xml_path),
            "davinci_edl": str(edl_path),
            "subtitles_srt": str(srt_path),
            "folder": str(vod_subfolder),
        }

    def build_profile(self, channel_name: str) -> ChannelProfile:
        """Derives and saves channel baseline profile from collected video analyses in DB."""
        return self.profiler.derive_profile(channel_name)

    def export_profile_json(
        self, channel_name_or_profile: str | ChannelProfile, output_path: str | Path
    ) -> Path:
        """Exports profile to a standalone local_profile.json file."""
        if isinstance(channel_name_or_profile, str):
            prof = self.db.get_profile(channel_name_or_profile) or self.profiler.derive_profile(channel_name_or_profile)
        else:
            prof = channel_name_or_profile
        return self.profiler.export_to_json(prof, output_path)

    def import_profile_json(
        self, json_path: str | Path, save_to_db: bool = True
    ) -> ChannelProfile:
        """Imports profile from a local_profile.json file."""
        return self.profiler.import_from_json(json_path, save_to_db=save_to_db)

    def export_markers(
        self,
        markers: list[ScanMarker],
        vod_path: str,
        output_path: str,
        export_format: str = "xml",
    ) -> str:
        return str(
            self.exporter.export(
                markers, vod_path, output_path, export_format=export_format
            )
        )

    def export_subtitles(self, subtitles: list[SubtitleItem], output_path: str) -> str:
        return str(self.subtitle_engine.export_srt(subtitles, output_path))


    def derive_two_track_profiles(
        self, channel_name: str
    ) -> tuple[ChannelProfile, ChannelProfile]:
        return self.profiler.derive_two_track_profiles(channel_name)

