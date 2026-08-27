"""Zero-Disk Lightweight In-Memory Avatar Visual Emotion & Motion Engine."""

from channel_dna.core.logger import get_logger

_logger = get_logger(__name__)

import os
import subprocess

import cv2
import numpy as np

from channel_dna.core.chzzk_client import (
    STEALTH_USER_AGENTS,
    get_chzzk_direct_lowres_video_url,
)


class VisionEmotionEngine:
    """Streams 144p/360p video frames into RAM (0MB disk usage) and extracts visual expression/motion curve."""

    def __init__(self, sample_fps: float = 1.0):
        self.sample_fps = sample_fps

    def extract_visual_emotion_curve(
        self, vod_path: str, duration_sec: float, progress_cb=None, cancel_event=None
    ) -> np.ndarray:
        """Samples 1 frame per second via in-memory FFmpeg pipe and computes avatar visual activity curve."""
        video_url = get_chzzk_direct_lowres_video_url(vod_path) or vod_path

        total_frames = int(duration_sec * self.sample_fps)
        visual_scores = np.zeros(total_frames, dtype=np.float32)

        if not video_url:
            return visual_scores

        if progress_cb:
            progress_cb(
                "VisionScan",
                0.05,
                "치지직 144p 인메모리 비전 스트림 수집 및 표정 감지 준비 중...",
            )

        # FFmpeg command: stream 144p/256px frames as raw JPEG images to stdout pipe
        cmd = ["ffmpeg", "-v", "error"]
        if video_url.startswith("http://") or video_url.startswith("https://"):
            cmd.extend(
                [
                    "-extension_picky",
                    "0",
                    "-headers",
                    f"User-Agent: {STEALTH_USER_AGENTS[0]}\r\nOrigin: https://chzzk.naver.com\r\n",
                ]
            )
        cmd.extend(
            [
                "-i",
                video_url,
                "-vf",
                f"fps={self.sample_fps},scale=256:-1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "-q:v",
                "5",
                "-",
            ]
        )

        proc = None
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=10**7,
                creationflags=creationflags,
            )
            raw_bytes = bytearray()
            frame_idx = 0
            prev_gray = None

            while True:
                if cancel_event and cancel_event.is_set():
                    break

                chunk = proc.stdout.read(65536) if proc.stdout else None
                if not chunk:
                    break
                raw_bytes.extend(chunk)

                # Find JPEG SOI (0xFF 0xD8) and EOI (0xFF 0xD9)
                while True:
                    soi = raw_bytes.find(b"\xff\xd8")
                    if soi == -1:
                        break
                    eoi = raw_bytes.find(b"\xff\xd9", soi + 2)
                    if eoi == -1:
                        break

                    jpeg_data = raw_bytes[soi : eoi + 2]
                    raw_bytes = raw_bytes[eoi + 2 :]

                    # Decode single frame from RAM
                    img_array = np.frombuffer(jpeg_data, dtype=np.uint8)
                    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

                    if frame is not None:
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                        score = 0.0
                        if prev_gray is not None and prev_gray.shape == gray.shape:
                            # 1. Optical Difference / Motion in Avatar area
                            diff = cv2.absdiff(prev_gray, gray)
                            motion_val = float(np.mean(diff))

                            # 2. High Frequency Edge Changes (Laugh/Opening mouth/Eyes)
                            lap = cv2.Laplacian(gray, cv2.CV_64F)
                            detail_val = float(np.var(lap))

                            # Combine into normalized visual dopamine score
                            score = (motion_val * 0.4) + (detail_val * 0.001)

                        prev_gray = gray

                        if frame_idx < total_frames:
                            visual_scores[frame_idx] = score

                        frame_idx += 1

                        if progress_cb and frame_idx % 200 == 0:
                            pct = min(0.95, (frame_idx / max(1, total_frames)) * 0.9)
                            progress_cb(
                                "VisionScan",
                                pct,
                                f"아바타 표정/움직임 분석 중: [{frame_idx}/{total_frames}초]...",
                            )

        except Exception as e:
            _logger.debug("Silenced exception: %s", e)
        finally:
            if proc is not None:
                try:
                    if proc.stdout:
                        proc.stdout.close()
                except Exception as e:
                    _logger.debug("Silenced exception: %s", e)
                try:
                    proc.kill()
                    proc.wait(timeout=1.0)
                except Exception as e:
                    _logger.debug("Silenced exception: %s", e)

        # Smooth curve
        if len(visual_scores) > 5:
            kernel = np.hanning(5)
            kernel /= kernel.sum()
            visual_scores = np.convolve(visual_scores, kernel, mode="same")

        if np.max(visual_scores) > 0:
            norm_visual = visual_scores / (
                np.percentile(visual_scores[visual_scores > 0], 90) or 1.0
            )
        else:
            norm_visual = visual_scores

        return norm_visual[: int(duration_sec)]

