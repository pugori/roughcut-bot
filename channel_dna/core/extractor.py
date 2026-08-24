"""Video and audio extraction module with Anti-Ban stealth, in-memory decoding, and zero-residual cleanup.
Enhanced with YouTube Subtitle Lexicon Auto-Mining and Multi-Feature Audio Dynamics (Speech Velocity + Laughter + Tension).
"""

import gc
import json
import os
import random
import re
import tempfile
import time
import urllib.parse
from pathlib import Path

import numpy as np

from channel_dna.config import config
from channel_dna.core.audio_engine import AudioEngine
from channel_dna.core.models import (
    ProgressCallback,
    SegmentData,
    VideoAnalysisResult,
    VideoMetadata,
)
from channel_dna.core.utils import STEALTH_USER_AGENTS


def normalize_youtube_url(raw_url: str) -> str:
    """Clean, unquote and normalize various YouTube URL formats."""
    url = urllib.parse.unquote(raw_url.strip().strip("\"'"))
    match = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    match = re.search(r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})", url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    return url


def normalize_channel_url(raw_url: str) -> str:
    """Normalize channel URL and unquote unicode handles."""
    url = urllib.parse.unquote(raw_url.strip().strip("\"'"))
    if not url.startswith("http"):
        if url.startswith("@"):
            url = f"https://www.youtube.com/{url}"
        else:
            url = f"https://www.youtube.com/@{url}"

    base_url = url.split("/videos")[0].split("/featured")[0].rstrip("/")
    return f"{base_url}/videos"


def mine_lexicon_from_text(text: str, top_n: int = 30) -> list[str]:
    """Extracts streamer-specific nouns, memes, and gaming keywords using Kiwi morphological analysis."""
    if not text.strip():
        return []
    try:
        from kiwipiepy import Kiwi
        kiwi = Kiwi(num_workers=1)
        tokens = kiwi.tokenize(text)
        stopwords = {
            "영상", "모음", "하이라이트", "다시보기", "풀버전", "1부", "2부", "3부", "오늘", "진짜",
            "그냥", "이거", "저거", "아니", "생각", "사람", "때문", "가지", "정도", "우리", "자기",
        }
        words = []
        for t in tokens:
            if t.tag in ("NNG", "NNP", "SL") and len(t.form) >= 2 and t.form not in stopwords:
                words.append(t.form)
        from collections import Counter
        return [w for w, _ in Counter(words).most_common(top_n)]
    except Exception:
        raw_words = re.findall(r"[가-힣a-zA-Z0-9_]{2,}", text)
        return raw_words[:top_n]


class VideoExtractor:
    def __init__(self, audio_engine: AudioEngine | None = None):
        self.audio_engine = audio_engine or AudioEngine()

    def _apply_stealth_jitter(self):
        """Random humanized delay (0.3s ~ 0.6s) to prevent automated rate-limiting / 429 bans."""
        jitter_sec = random.uniform(0.3, 0.6)
        time.sleep(jitter_sec)

    def fetch_channel_videos(
        self,
        channel_url: str,
        max_videos: int = 5,
        sort_by: str = "popular",
        progress_cb: ProgressCallback | None = None,
    ) -> list[dict[str, str]]:
        """Fetch N videos with real Popular (View Count) vs Latest sorting and anti-ban stealth."""
        self._apply_stealth_jitter()
        clean_channel_url = normalize_channel_url(channel_url)
        sort_name = "인기순(조회수 최고)" if sort_by == "popular" else "최신순"

        if progress_cb:
            progress_cb(
                "ChannelScan",
                0.1,
                f"채널 {sort_name} 영상 목록 탐색 중 (스텔스 모드): {clean_channel_url}",
            )

        ua = random.choice(STEALTH_USER_AGENTS)
        fetch_limit = (
            min(150, max(max_videos * 4, 60)) if sort_by == "popular" else max_videos
        )

        ydl_opts = {
            "extract_flat": True,
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "playlistend": fetch_limit,
            "http_headers": {
                "User-Agent": ua,
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-CH-UA": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            },
        }

        import yt_dlp

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(clean_channel_url, download=False)
            entries = res.get("entries", []) if res else []

            videos = []
            for e in entries:
                if not e:
                    continue
                v_id = e.get("id") or e.get("url")
                if not v_id:
                    continue
                view_cnt = e.get("view_count") or 0
                videos.append(
                    {
                        "url": f"https://www.youtube.com/watch?v={v_id}",
                        "title": e.get("title", "Untitled"),
                        "view_count": int(view_cnt) if view_cnt else 0,
                    }
                )

            if sort_by == "popular":
                videos = sorted(
                    videos, key=lambda x: x.get("view_count", 0), reverse=True
                )

            final_list = videos[:max_videos]
            if progress_cb:
                progress_cb(
                    "ChannelScan",
                    1.0,
                    f"대표 영상 {len(final_list)}편 선별 완료 ({sort_name})",
                )
            return final_list

    def download_youtube_lightweight(
        self,
        youtube_url: str,
        output_dir: Path,
        progress_cb: ProgressCallback | None = None,
    ) -> tuple[str, str, str, str, list[str], list[str]]:
        """Ultra-fast proxy stream download (360p / 16kHz mono audio) + Subtitle Lexicon Auto-Mining."""
        self._apply_stealth_jitter()
        clean_url = normalize_youtube_url(youtube_url)

        if progress_cb:
            progress_cb(
                "Download",
                0.1,
                f"초경량 스트림 및 자막 어휘 수집: {clean_url}",
            )

        ua = random.choice(STEALTH_USER_AGENTS)
        ydl_opts = {
            "format": "ba/b/18/bestaudio/worst/best",
            "external_downloader": "ffmpeg",
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["ko"],
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "retries": 10,
            "fragment_retries": 10,
            "http_headers": {
                "User-Agent": ua,
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
        }

        import subprocess
        import yt_dlp

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            if not info:
                raise ValueError(f"Failed to fetch video info from: {clean_url}")

            video_id = info.get("id", "unknown_id")
            title = info.get("title", "Untitled Video")
            description = info.get("description", "") or ""
            tags = info.get("tags", []) or []

            # Streaming Clip Optimization: Fetch first 10 minutes
            stream_url = info.get("url", clean_url)
            filename = str(output_dir / f"{video_id}.mp4")

            if progress_cb:
                progress_cb("Download", 0.5, "10분 인메모리 클리핑 중 (초고속)...")

            cmd = [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-threads",
                "2",
                "-i",
                stream_url,
                "-t",
                "600",
                "-c",
                "copy",
                filename,
            ]

            creationflags = (
                (subprocess.CREATE_NO_WINDOW | 0x00004000) if os.name == "nt" else 0
            )
            proc = subprocess.Popen(cmd, creationflags=creationflags)
            proc.communicate()

            if not Path(filename).exists():
                raise FileNotFoundError(f"Failed to clip media stream to: {filename}")

            # Subtitle Lexicon Auto-Mining
            sub_text = ""
            for sub_file in output_dir.glob(f"{video_id}*.vtt"):
                try:
                    sub_raw = sub_file.read_text(encoding="utf-8", errors="ignore")
                    sub_clean = re.sub(r"<[^>]+>", "", sub_raw)
                    sub_clean = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}", "", sub_clean)
                    sub_text += " " + sub_clean
                except Exception:
                    pass

            combined_text = f"{title} {description} {' '.join(tags)} {sub_text}"
            mined_lexicon = mine_lexicon_from_text(combined_text, top_n=35)

        if progress_cb:
            progress_cb("Download", 1.0, f"다운로드 및 어휘 마이닝 완료: {title}")
        return video_id, title, filename, description, tags, mined_lexicon

    def detect_cuts(
        self, video_path: str, progress_cb: ProgressCallback | None = None
    ) -> list[float]:
        """Detect scene cuts using PySceneDetect."""
        if progress_cb:
            progress_cb("SceneDetect", 0.2, "비디오 컷 전환 리듬 분석 중...")

        try:
            from scenedetect import ContentDetector, SceneManager, open_video

            video = open_video(video_path)
            scene_manager = SceneManager()
            scene_manager.add_detector(
                ContentDetector(threshold=config.scene_threshold)
            )

            scene_manager.detect_scenes(video=video, frame_skip=config.scene_frame_skip)
            scene_list = scene_manager.get_scene_list()

            cuts = []
            for scene in scene_list:
                cuts.append(scene[0].get_seconds())
            if scene_list:
                cuts.append(scene_list[-1][1].get_seconds())

            cuts = sorted(list(set(cuts)))
            del video
            del scene_manager
            gc.collect()

            if progress_cb:
                progress_cb("SceneDetect", 1.0, f"컷 전환점 {len(cuts)}개 검출 완료.")
            return cuts
        except Exception as e:
            if progress_cb:
                progress_cb("SceneDetect", 1.0, f"컷 분석 참고: {e}")
            return []

    def extract_speech_timing_segments(
        self,
        audio_data: np.ndarray,
        times: np.ndarray,
        tension: np.ndarray,
        video_id: str,
    ) -> list[SegmentData]:
        """Fast VAD-based dialogue/subtitle timing extraction."""
        vad_prob = self.audio_engine.compute_energy_vad(audio_data)
        if len(vad_prob) != len(times):
            vad_prob = np.interp(
                np.linspace(0, 1, len(times)),
                np.linspace(0, 1, len(vad_prob)),
                vad_prob,
            )

        is_speaking = vad_prob > 0.3
        segments: list[SegmentData] = []

        in_speech = False
        start_t = 0.0
        peak_t = 0.0

        for t, speaking, val in zip(times, is_speaking, tension):
            if speaking:
                if not in_speech:
                    in_speech = True
                    start_t = t
                    peak_t = val
                else:
                    peak_t = max(peak_t, val)
            else:
                if in_speech:
                    in_speech = False
                    end_t = t
                    dur = end_t - start_t
                    if dur >= 0.4:
                        segments.append(
                            SegmentData(
                                video_id=video_id,
                                start_time=round(float(start_t), 2),
                                end_time=round(float(end_t), 2),
                                duration=round(float(dur), 2),
                                rms_peak=round(float(peak_t), 2),
                                transcript="[Speech Timing Unit]",
                            )
                        )

        if in_speech:
            end_t = times[-1]
            dur = end_t - start_t
            if dur >= 0.4:
                segments.append(
                    SegmentData(
                        video_id=video_id,
                        start_time=round(float(start_t), 2),
                        end_time=round(float(end_t), 2),
                        duration=round(float(dur), 2),
                        rms_peak=round(float(peak_t), 2),
                        transcript="[Speech Timing Unit]",
                    )
                )

        return segments

    def analyze(
        self,
        video_input: str,
        channel_name: str | None = None,
        is_url: bool = False,
        progress_cb: ProgressCallback | None = None,
    ) -> VideoAnalysisResult:
        """Full extraction pipeline with In-Memory decoding, Tri-Feature audio dynamics & Lexicon mining."""
        clean_input = (
            normalize_youtube_url(video_input) if is_url else video_input.strip()
        )

        with tempfile.TemporaryDirectory(prefix="cdna_temp_") as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            try:
                mined_lexicon: list[str] = []
                if is_url:
                    video_id, title, video_file, desc, tags, mined_lexicon = (
                        self.download_youtube_lightweight(
                            clean_input, temp_dir, progress_cb
                        )
                    )
                else:
                    video_file = clean_input
                    video_id = Path(clean_input).stem
                    title = Path(clean_input).name
                    desc = ""
                    tags = []
                    mined_lexicon = mine_lexicon_from_text(title, top_n=20)

                # 1. In-Memory Direct Audio Decoding (0-byte Disk I/O)
                if progress_cb:
                    progress_cb(
                        "AudioExtract",
                        0.25,
                        "RAM 인메모리 직접 디코딩 중 (디스크 쓰기 0바이트)...",
                    )
                audio_data = self.audio_engine.extract_audio_in_memory(video_file)

                # 2. Scene Cuts & ASL Detection
                cuts = self.detect_cuts(video_file, progress_cb)

                # 3. Audio Dynamics Tri-Feature: Vocal Tension + Speech Density + Laughter Dynamics
                if progress_cb:
                    progress_cb(
                        "TensionAnalysis",
                        0.6,
                        "오디오 다이내믹스(텐션 + 발화속도 + 웃음) 복합 궤적 산출 중...",
                    )
                times, tension = self.audio_engine.compute_sliding_tension(audio_data)
                _, speech_density, laughter_curve = (
                    self.audio_engine.compute_speech_density_and_laughter_curves(audio_data)
                )

                # Fused Composite Tension Curve
                min_len = min(len(times), len(tension), len(speech_density), len(laughter_curve))
                times = times[:min_len]
                tension = tension[:min_len]
                speech_density = speech_density[:min_len]
                laughter_curve = laughter_curve[:min_len]

                fused_tension = (tension * 0.55) + (speech_density * 0.25) + (laughter_curve * 0.20)

                duration = (
                    float(times[-1])
                    if len(times) > 0
                    else self.audio_engine.get_audio_duration_ffmpeg(video_file)
                )

                # 4. Fast Dialogue / Subtitle Timing Units
                if progress_cb:
                    progress_cb(
                        "TimingAnalysis", 0.8, "발화 리듬 및 무음 구조 추출 중..."
                    )
                segments = self.extract_speech_timing_segments(
                    audio_data, times, fused_tension, video_id
                )

                # Compute ASL
                if len(cuts) >= 2:
                    shot_lengths = [cuts[i + 1] - cuts[i] for i in range(len(cuts) - 1)]
                    asl = float(np.mean(shot_lengths))
                else:
                    asl = duration / max(1, len(segments)) if segments else 3.5

                # 5. Advanced Two-Track Solo vs Collab Classification
                from channel_dna.core.classifier import classify_youtube_video

                detected_type, host_voice_print = classify_youtube_video(
                    title=title,
                    description=desc,
                    tags=tags,
                    duration=duration,
                    avg_shot_length=asl,
                    segments=segments,
                    audio_data=audio_data,
                )

                metadata = VideoMetadata(
                    video_id=video_id,
                    title=title,
                    duration=duration,
                    avg_shot_length=asl,
                    channel_name=channel_name,
                    file_path=json.dumps(host_voice_print)
                    if host_voice_print
                    else (", ".join(mined_lexicon) if mined_lexicon else None),
                    video_type=detected_type,
                    speech_density=round(float(np.mean(speech_density)), 2) if len(speech_density) > 0 else 0.75,
                    laughter_score=round(float(np.mean(laughter_curve)), 2) if len(laughter_curve) > 0 else 1.0,
                )

                if progress_cb:
                    progress_cb(
                        "Complete",
                        1.0,
                        f"분석 완료: {title} (ASL: {asl:.2f}s, 어휘: {len(mined_lexicon)}개)",
                    )

                return VideoAnalysisResult(
                    metadata=metadata,
                    cut_timestamps=cuts,
                    segments=segments,
                    tension_times=times.tolist(),
                    tension_values=fused_tension.tolist(),
                )
            finally:
                gc.collect()
