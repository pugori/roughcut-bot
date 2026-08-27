"""High-performance Rough Cut Video Renderer using FFmpeg.

Slices all detected highlight markers from the VOD and seamlessly concatenates them
into a single continuous, ready-to-watch full rough cut video (.mp4) with audio edge de-clicking.
"""

from channel_dna_local.core.logger import get_logger

_logger = get_logger(__name__)

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from channel_dna_local.core.models import ProgressCallback, ScanMarker


class RoughCutRenderer:
    """Renders full rough cut MP4 videos from scan markers using FFmpeg."""

    def __init__(self):
        self.ffmpeg_cmd = shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_cmd = shutil.which("ffprobe") or "ffprobe"

    def _resolve_source_media(self, vod_path: str) -> str:
        s = str(vod_path).strip()
        # 1. Local file path check
        p = Path(s)
        if p.exists() and p.is_file():
            return str(p.resolve())

        # 2. Web stream / URL check (Chzzk, YouTube, etc.)
        if "http://" in s or "https://" in s or (s.isdigit() and len(s) >= 7):
            try:
                import yt_dlp

                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(s, download=False)
                    if info and info.get("url"):
                        return info["url"]
            except Exception as e:
                print(f"[RoughCutRenderer] yt_dlp stream resolve notice: {e}")
        return s

    def render_full_rough_cut(
        self,
        vod_path: str,
        markers: list[ScanMarker],
        output_mp4_path: str,
        progress_cb: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Slices all marker intervals and concatenates them into a single rough cut MP4."""
        out_file = Path(output_mp4_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        if not markers:
            raise ValueError("렌더링할 하이라이트 마커가 없습니다.")

        resolved_source = self._resolve_source_media(vod_path)
        if not resolved_source:
            raise ValueError("영상 원본 경로(또는 스트림 주소)를 찾을 수 없습니다.")

        # Check local path validity
        if not ("http://" in resolved_source or "https://" in resolved_source):
            if not Path(resolved_source).exists():
                raise FileNotFoundError(
                    f"로컬 영상 원본 파일을 찾을 수 없습니다: {resolved_source}"
                )

        total_markers = len(markers)

        if progress_cb:
            progress_cb(
                "RoughCut",
                0.05,
                f"총 {total_markers}개 하이라이트 구간 컷편집 렌더링 준비 중...",
            )

        temp_dir = Path(tempfile.mkdtemp(prefix="dna_roughcut_"))
        clip_files: list[Path] = []
        last_error_log = ""

        try:
            for idx, m in enumerate(markers):
                if cancel_event and cancel_event.is_set():
                    raise RuntimeError(
                        "사용자에 의해 컷편집 영상 생성이 중단되었습니다."
                    )

                clip_path = temp_dir / f"clip_{idx:04d}.mp4"
                dur = max(0.5, m.end_time - m.start_time)
                fade_dur = min(0.08, dur * 0.20)
                out_fade_st = max(0.0, dur - fade_dur)

                # Audio filter to smoothly fade in/out and eliminate popping noise
                af_filter = f"afade=t=in:st=0:d={fade_dur:.2f},afade=t=out:st={out_fade_st:.2f}:d={fade_dur:.2f}"

                # FFmpeg accurate slice command with fixed 30fps fast encoding for demo sample efficiency
                cmd = [
                    self.ffmpeg_cmd,
                    "-y",
                    "-ss",
                    f"{m.start_time:.3f}",
                    "-i",
                    resolved_source,
                    "-t",
                    f"{dur:.3f}",
                    "-r",
                    "30",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "22",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-af",
                    af_filter,
                    "-avoid_negative_ts",
                    "make_zero",
                    "-movflags",
                    "+faststart",
                    str(clip_path.resolve()),
                ]

                # Run slice process safely with timeout
                try:
                    res = subprocess.run(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NO_WINDOW
                        if os.name == "nt"
                        else 0,
                        timeout=180,
                    )
                    if res.returncode != 0 and res.stderr:
                        last_error_log = res.stderr.decode("utf-8", errors="ignore")[
                            -300:
                        ]
                except subprocess.TimeoutExpired:
                    last_error_log = "FFmpeg 슬라이스 작업 시간 초과"

                # Fallback: if complex audio filter failed, try direct slice
                if not clip_path.exists() or clip_path.stat().st_size < 1000:
                    fallback_cmd = [
                        self.ffmpeg_cmd,
                        "-y",
                        "-ss",
                        f"{m.start_time:.3f}",
                        "-i",
                        resolved_source,
                        "-t",
                        f"{dur:.3f}",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "ultrafast",
                        "-crf",
                        "24",
                        "-c:a",
                        "aac",
                        str(clip_path.resolve()),
                    ]
                    try:
                        res_fb = subprocess.run(
                            fallback_cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            creationflags=subprocess.CREATE_NO_WINDOW
                            if os.name == "nt"
                            else 0,
                            timeout=180,
                        )
                        if res_fb.returncode != 0 and res_fb.stderr:
                            last_error_log = res_fb.stderr.decode(
                                "utf-8", errors="ignore"
                            )[-300:]
                    except subprocess.TimeoutExpired:
                        last_error_log = "FFmpeg 슬라이스 대체 작업 시간 초과"

                if clip_path.exists() and clip_path.stat().st_size > 1000:
                    clip_files.append(clip_path)

                if progress_cb:
                    ratio = 0.05 + (0.80 * (idx + 1) / total_markers)
                    progress_cb(
                        "RoughCut",
                        ratio,
                        f"구간 컷팅 중 ({idx + 1}/{total_markers}): {int(m.start_time // 60)}분 {int(m.start_time % 60)}초 ~ {int(m.end_time // 60)}분",
                    )

            if not clip_files:
                err_detail = (
                    f"\nFFmpeg 오류: {last_error_log}" if last_error_log else ""
                )
                raise RuntimeError(
                    f"구간 슬라이스 클립 생성에 실패했습니다.{err_detail}"
                )

            if cancel_event and cancel_event.is_set():
                raise RuntimeError("사용자에 의해 컷편집 영상 생성이 중단되었습니다.")

            if progress_cb:
                progress_cb(
                    "RoughCut",
                    0.88,
                    f"총 {len(clip_files)}개 클립 최종 풀 영상 병합 중...",
                )

            # Write concat demuxer list (Use forward slashes for cross-platform ffmpeg concat)
            concat_list_file = temp_dir / "concat_list.txt"
            concat_lines = [f"file '{c.resolve().as_posix()}'" for c in clip_files]
            concat_list_file.write_text("\n".join(concat_lines), encoding="utf-8")

            # Concat demuxer (lossless & instant)
            concat_cmd = [
                self.ffmpeg_cmd,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_file.resolve()),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(out_file.resolve()),
            ]

            res_concat = subprocess.run(
                concat_cmd,
                cwd=str(temp_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                timeout=300,
            )

            if not out_file.exists() or out_file.stat().st_size < 1000:
                err_concat_msg = (
                    res_concat.stderr.decode("utf-8", errors="ignore")[-300:]
                    if res_concat.stderr
                    else ""
                )
                raise RuntimeError(
                    f"최종 러프컷 영상 병합 파일이 생성되지 않았습니다. {err_concat_msg}"
                )

            if progress_cb:
                progress_cb("Complete", 1.0, f"🎬 풀 컷편집 영상 완성: {out_file.name}")

            return out_file

        finally:
            # Clean up temp folder
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)

