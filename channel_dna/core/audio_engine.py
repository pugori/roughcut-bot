"""High-performance Audio Engine with Multiband Vocal Isolation and Robust YouTube/Chzzk Stream Decoders."""

from channel_dna.core.logger import get_logger

_logger = get_logger(__name__)

import gc
import logging
import os
import shutil
import subprocess
import time
from typing import Any

import numpy as np
from scipy.signal import butter, sosfilt


def njit(*args, **kwargs):
    """Lazy Numba JIT wrapper to prevent multi-second LLVM compiler import overhead during app startup."""

    def decorator(fn):
        _compiled = None

        def wrapper(*w_args, **w_kwargs):
            nonlocal _compiled
            if _compiled is None:
                try:
                    from numba import njit as _real_njit

                    _compiled = _real_njit(*args, **kwargs)(fn)
                except Exception:
                    _compiled = fn
            return _compiled(*w_args, **w_kwargs)

        return wrapper

    if len(args) == 1 and callable(args[0]):
        fn = args[0]
        return njit()(fn)
    return decorator


from channel_dna.config import config
from channel_dna.core.chzzk_client import get_chzzk_direct_audio_url

try:
    import channel_dna_native

    _HAS_RUST_NATIVE = True
except Exception:
    _HAS_RUST_NATIVE = False


@njit(fastmath=True)
def _numba_sliding_rms_tension(
    samples: np.ndarray, window_len: int, hop_len: int
) -> tuple[np.ndarray, np.ndarray]:
    n_samples = len(samples)
    if n_samples < window_len:
        return np.zeros(1, dtype=np.float32), np.zeros(1, dtype=np.float32)

    n_frames = (n_samples - window_len) // hop_len + 1
    times = np.zeros(n_frames, dtype=np.float32)
    tensions = np.zeros(n_frames, dtype=np.float32)

    inv_sr = 1.0 / 16000.0
    inv_window = 1.0 / window_len

    for i in range(n_frames):
        start_idx = i * hop_len
        end_idx = start_idx + window_len

        sq_sum = 0.0
        for j in range(start_idx, end_idx):
            val = samples[j]
            sq_sum += val * val

        rms = np.sqrt(sq_sum * inv_window)
        times[i] = (start_idx + end_idx) * 0.5 * inv_sr
        tensions[i] = rms

    return times, tensions


def fast_sliding_rms_tension(
    samples: np.ndarray, window_len: int, hop_len: int
) -> tuple[np.ndarray, np.ndarray]:
    if _HAS_RUST_NATIVE:
        try:
            return channel_dna_native.fast_sliding_rms_tension_rs(
                np.ascontiguousarray(samples, dtype=np.float32), window_len, hop_len
            )
        except Exception as e:
            _logger.debug("Silenced exception: %s", e)
    return _numba_sliding_rms_tension(samples, window_len, hop_len)


@njit(fastmath=True)
def fast_multifeature_tension(
    vocal_rms: np.ndarray,
    total_rms: np.ndarray,
    vocal_samples: np.ndarray,
    window_len: int,
    hop_len: int,
) -> np.ndarray:
    """Numba C-JIT Multi-Feature Vocal Tension: Blends Vocal Purity (40%), Speech Density/Rate (30%), Energy Flux (15%), and Pitch/Arousal Modulation (15%)."""
    n = len(vocal_rms)
    tension = np.zeros(n, dtype=np.float32)

    for i in range(n):
        tot = total_rms[i]
        voc = vocal_rms[i]

        # 1. Vocal Purity
        purity = (voc / tot) if tot > 1e-5 else 0.0
        purity_score = voc * (0.35 + 0.65 * purity)

        # 2. Speech Density (Zero-Crossing Rate in vocal formant for speech cadence & pitch arousal)
        s_idx = i * hop_len
        e_idx = min(len(vocal_samples), s_idx + window_len)
        zcr = 0.0
        if e_idx > s_idx + 1:
            crossings = 0
            for j in range(s_idx, e_idx - 1):
                if (vocal_samples[j] >= 0 and vocal_samples[j + 1] < 0) or (
                    vocal_samples[j] < 0 and vocal_samples[j + 1] >= 0
                ):
                    crossings += 1
            zcr = float(crossings) / float(e_idx - s_idx)

        # High cadence speech & pitch rise (fast dialogue / wit): ZCR around 0.07~0.28
        cadence_score = 1.0 + 0.65 * np.sin(
            np.pi * min(1.0, max(0.0, (zcr - 0.03) / 0.18))
        )

        # 3. Energy Delta (Sudden reaction / Punchline burst)
        flux_score = 1.0
        if i > 0:
            diff = voc - vocal_rms[i - 1]
            if diff > 0.003:
                flux_score = 1.0 + min(1.8, diff * 60.0)

        tension[i] = purity_score * cadence_score * flux_score

    return tension


@njit(fastmath=True)
def fast_vocal_purity_ratio(vocal_rms: np.ndarray, total_rms: np.ndarray) -> np.ndarray:
    n = len(vocal_rms)
    pure_tension = np.zeros(n, dtype=np.float32)
    for i in range(n):
        tot = total_rms[i]
        voc = vocal_rms[i]
        if tot > 1e-5:
            ratio = voc / tot
            pure_tension[i] = voc * (0.5 + 0.5 * ratio)
        else:
            pure_tension[i] = 0.0
    return pure_tension


class AudioEngine:
    def __init__(self, sr: int = 16000):
        self.sr = sr
        self.ffmpeg_cmd = shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_cmd = shutil.which("ffprobe") or "ffprobe"

        self.sos_vocal = butter(
            4, [300.0, 3400.0], btype="bandpass", fs=self.sr, output="sos"
        )
        self.sos_game_bass = butter(
            4, [40.0, 250.0], btype="bandpass", fs=self.sr, output="sos"
        )
        # Phase 2: Presence band for screams, high-pitch reactions (3400-7500Hz)
        self.sos_presence = butter(
            4,
            [3400.0, min(7500.0, self.sr * 0.49)],
            btype="bandpass",
            fs=self.sr,
            output="sos",
        )

        self.cache_dir = config.default_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load_cache(self, file_id: str) -> tuple[np.ndarray, np.ndarray] | None:
        cache_file = self.cache_dir / f"{file_id}_tension.npz"
        if cache_file.exists():
            try:
                data = np.load(cache_file)
                return data["times"], data["tension"]
            except Exception:
                return None
        return None

    def save_cache(self, file_id: str, times: np.ndarray, tension: np.ndarray):
        try:
            cache_file = self.cache_dir / f"{file_id}_tension.npz"
            np.savez_compressed(cache_file, times=times, tension=tension)
        except Exception as e:
            _logger.debug("Silenced exception: %s", e)

    def _resolve_stream_url(self, source_path: str) -> str:
        s = str(source_path).strip()
        if "chzzk.naver.com" in s or (s.isdigit() and len(s) >= 7):
            direct_url = get_chzzk_direct_audio_url(s)
            if direct_url:
                return direct_url
            else:
                raise RuntimeError(
                    f"치지직 VOD 스트림 주소 추출 실패: 영상 주소({s})에서 재생 스트림을 찾지 못했습니다."
                )
        elif "youtube.com" in s or "youtu.be" in s:
            try:
                import yt_dlp

                ydl_opts = {
                    "format": "bestaudio/best",
                    "quiet": True,
                    "extractor_args": {
                        "youtube": {"player_client": ["android", "web"]}
                    },
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(s, download=False)
                    return info.get("url", s)
            except Exception as e:
                logging.getLogger(__name__).warning(f"YouTube URL extract failed: {e}")
        return s

    def _build_ffmpeg_cmd(
        self, url: str, max_duration_sec: float | None = None
    ) -> list:
        cmd = [self.ffmpeg_cmd, "-v", "error", "-threads", "4"]
        if url.startswith("http://") or url.startswith("https://"):
            headers = "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\nReferer: https://chzzk.naver.com/\r\n"
            if ".m3u8" in url:
                cmd.extend(
                    [
                        "-extension_picky",
                        "0",
                        "-reconnect",
                        "1",
                        "-reconnect_streamed",
                        "1",
                        "-reconnect_delay_max",
                        "5",
                    ]
                )
            cmd.extend(["-headers", headers])

        if max_duration_sec:
            cmd.extend(["-t", str(max_duration_sec)])

        # Handle Windows local path with special characters / unicode (use 8.3 Short Path to avoid FFmpeg illegal byte sequence)
        clean_input = url
        if not (url.startswith("http://") or url.startswith("https://")):
            clean_input = os.path.abspath(url)
            if os.name == "nt" and os.path.exists(clean_input):
                try:
                    import ctypes
                    buf = ctypes.create_unicode_buffer(1024)
                    if ctypes.windll.kernel32.GetShortPathNameW(clean_input, buf, 1024) > 0:
                        clean_input = buf.value
                except Exception:
                    pass

        cmd.extend(
            [
                "-i",
                clean_input,
                "-vn",
                "-f",
                "s16le",
                "-acodec",
                "pcm_s16le",
                "-ar",
                str(self.sr),
                "-ac",
                "1",
                "pipe:1",
            ]
        )
        return cmd

    def extract_audio_in_memory(
        self,
        source_path: str,
        max_duration_sec: float | None = None,
        progress_cb: Any | None = None,
        cancel_event: Any | None = None,
        expected_duration_sec: float | None = None,
    ) -> np.ndarray:
        if progress_cb:
            progress_cb(
                "AudioExtract", 0.05, "오디오 스트림 분석 및 파이프라인 연결 중..."
            )

        s = self._resolve_stream_url(source_path)

        cmd = self._build_ffmpeg_cmd(s, max_duration_sec)

        # 0x00004000 = BELOW_NORMAL_PRIORITY_CLASS (Prevents freezing foreground apps like Chrome)
        creationflags = (
            (subprocess.CREATE_NO_WINDOW | 0x00004000) if os.name == "nt" else 0
        )
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )

        chunks = []
        total_bytes = 0
        chunk_size = self.sr * 2 * 2  # 2 seconds of 16-bit audio per read

        start_time = time.time()
        last_progress_time = 0.0

        try:
            while True:
                if cancel_event and cancel_event.is_set():
                    try:
                        proc.kill()
                    except Exception as e:
                        _logger.debug("Silenced exception: %s", e)
                    return np.zeros(0, dtype=np.float32)

                data = proc.stdout.read(chunk_size)
                if not data:
                    break
                chunks.append(data)
                total_bytes += len(data)

                now = time.time()
                if progress_cb and (now - last_progress_time >= 0.5):
                    last_progress_time = now
                    curr_sec = total_bytes / (self.sr * 2)
                    elapsed = max(0.1, now - start_time)
                    speed = curr_sec / elapsed if elapsed > 0 else 0.0

                    if expected_duration_sec and expected_duration_sec > 0:
                        pct = min(0.99, curr_sec / expected_duration_sec)
                        c_h, c_m, c_s = (
                            int(curr_sec // 3600),
                            int((curr_sec % 3600) // 60),
                            int(curr_sec % 60),
                        )
                        t_h, t_m, t_s = (
                            int(expected_duration_sec // 3600),
                            int((expected_duration_sec % 3600) // 60),
                            int(expected_duration_sec % 60),
                        )
                        progress_cb(
                            "AudioScan",
                            0.10 + 0.25 * pct,
                            f"인메모리 수집: {c_h:02d}:{c_m:02d}:{c_s:02d} / {t_h:02d}:{t_m:02d}:{t_s:02d} ({pct * 100:.1f}%) [속도: {speed:.1f}x]",
                        )
                    else:
                        c_h, c_m, c_s = (
                            int(curr_sec // 3600),
                            int((curr_sec % 3600) // 60),
                            int(curr_sec % 60),
                        )
                        progress_cb(
                            "AudioScan",
                            0.15,
                            f"인메모리 오디오 수집 중: {c_h:02d}:{c_m:02d}:{c_s:02d} [속도: {speed:.1f}x]",
                        )

            proc.stdout.close()
            err = proc.stderr.read()
            proc.stderr.close()
            proc.wait()

            if proc.returncode != 0 and total_bytes == 0:
                raise RuntimeError(
                    f"FFmpeg in-memory decode failed: {err.decode('utf-8', errors='ignore')}"
                )
        finally:
            try:
                proc.kill()
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)

        # Memory-efficient chunk streaming into pre-allocated float32 (zero intermediate duplication)
        total_samples = total_bytes // 2
        samples = np.empty(total_samples, dtype=np.float32)
        offset = 0
        inv_scale = 1.0 / 32768.0
        for ch in chunks:
            arr = np.frombuffer(ch, dtype=np.int16)
            n = len(arr)
            samples[offset : offset + n] = arr.astype(np.float32) * inv_scale
            offset += n

        chunks.clear()
        del chunks
        gc.collect()
        return samples

    def extract_audio_slice(
        self, source_path: str, start_sec: float, end_sec: float
    ) -> np.ndarray:
        """High-speed single slice extraction using FFmpeg seeking (0.05s)."""
        dur = max(0.2, end_sec - start_sec)
        s = str(source_path).strip()
        if "chzzk.naver.com" in s or (s.isdigit() and len(s) >= 7):
            direct_url = get_chzzk_direct_audio_url(s)
            if direct_url:
                s = direct_url

        cmd = [
            self.ffmpeg_cmd,
            "-v",
            "error",
            "-ss",
            str(max(0.0, start_sec)),
            "-t",
            str(dur),
            "-i",
            s,
            "-vn",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(self.sr),
            "-ac",
            "1",
            "pipe:1",
        ]
        if s.startswith("http://") or s.startswith("https://"):
            cmd.insert(1, "-headers")
            cmd.insert(
                2,
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\nReferer: https://chzzk.naver.com/\r\n",
            )

        creationflags = (
            (subprocess.CREATE_NO_WINDOW | 0x00004000) if os.name == "nt" else 0
        )
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
            raw_bytes, _ = proc.communicate()
            if not raw_bytes:
                return np.zeros(0, dtype=np.float32)
            return np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        except Exception:
            return np.zeros(0, dtype=np.float32)

    def get_audio_duration_ffmpeg(self, source_path: str) -> float:
        cmd = [
            self.ffprobe_cmd,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source_path),
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                creationflags=creationflags,
            )
            return float(res.stdout.strip())
        except Exception:
            return 0.0

    def compute_sliding_tension(
        self, audio_data: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        if len(audio_data) < int(self.sr * 0.25):
            return np.zeros(1, dtype=np.float32), np.zeros(1, dtype=np.float32)

        window_len = int(self.sr * config.window_size_sec)
        hop_len = int(self.sr * config.hop_size_sec)

        times, total_rms = fast_sliding_rms_tension(audio_data, window_len, hop_len)

        vocal_samples = sosfilt(self.sos_vocal, audio_data).astype(np.float32)
        _, vocal_rms = fast_sliding_rms_tension(vocal_samples, window_len, hop_len)

        min_len = min(len(total_rms), len(vocal_rms))
        pure_vocal_tension = fast_multifeature_tension(
            vocal_rms[:min_len], total_rms[:min_len], vocal_samples, window_len, hop_len
        )

        # --- Phase 2: Multiband Enhancement ---
        # 1. Presence band (3400-7500Hz): screams, high-pitch reactions
        presence_samples = sosfilt(self.sos_presence, audio_data).astype(np.float32)
        _, presence_rms = fast_sliding_rms_tension(
            presence_samples, window_len, hop_len
        )

        # 2. Bass band (40-250Hz): impact, bass energy
        bass_samples = sosfilt(self.sos_game_bass, audio_data).astype(np.float32)
        _, bass_rms = fast_sliding_rms_tension(bass_samples, window_len, hop_len)

        # 3. Onset strength: detect sudden energy increases
        onset_strength = self._compute_onset_strength(total_rms[:min_len])

        # 4. Blend multiband features
        presence_len = min(min_len, len(presence_rms))
        bass_len = min(min_len, len(bass_rms))

        blended_tension = np.zeros(min_len, dtype=np.float32)

        w = config.multiband_weights
        w_vocal = w.get("vocal", 0.50)
        w_presence = w.get("presence", 0.25)
        w_bass = w.get("bass", 0.10)
        w_onset = w.get("onset", 0.15)

        blended_tension[:min_len] += pure_vocal_tension[:min_len] * w_vocal

        # Normalize and add presence band
        if presence_len > 0 and np.std(presence_rms[:presence_len]) > 1e-6:
            p_mean = np.mean(presence_rms[:presence_len])
            p_std = np.std(presence_rms[:presence_len])
            presence_norm = (presence_rms[:presence_len] - p_mean) / p_std
            blended_tension[:presence_len] += np.maximum(0, presence_norm) * w_presence

        # Normalize and add bass band
        if bass_len > 0 and np.std(bass_rms[:bass_len]) > 1e-6:
            b_mean = np.mean(bass_rms[:bass_len])
            b_std = np.std(bass_rms[:bass_len])
            bass_norm = (bass_rms[:bass_len] - b_mean) / b_std
            blended_tension[:bass_len] += np.maximum(0, bass_norm) * w_bass

        # Add onset strength
        if len(onset_strength) > 0:
            onset_len = min(min_len, len(onset_strength))
            blended_tension[:onset_len] += onset_strength[:onset_len] * w_onset

        # Final z-score normalization
        mean_v = float(np.mean(blended_tension))
        std_v = float(np.std(blended_tension))
        if std_v > 1e-6:
            tension_norm = (blended_tension - mean_v) / std_v
        else:
            tension_norm = np.zeros_like(blended_tension)

        return times[:min_len], tension_norm

    def compute_speech_density_and_laughter_curves(
        self, audio_data: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Computes continuous 1-second sliding Speech Density (0.0~1.0) and Laughter/Pitch Volatility curves."""
        if len(audio_data) < int(self.sr * 0.5):
            return np.zeros(1, dtype=np.float32), np.zeros(1, dtype=np.float32), np.zeros(1, dtype=np.float32)

        window_len = int(self.sr * config.window_size_sec) # 1.0s
        hop_len = int(self.sr * config.hop_size_sec)       # 0.5s

        # 1. Vocal formant filtering for speech detection
        vocal_samples = sosfilt(self.sos_vocal, audio_data).astype(np.float32)
        times, vocal_rms = fast_sliding_rms_tension(vocal_samples, window_len, hop_len)

        # 2. Presence/Laughter high-frequency band (2.5kHz ~ 5.5kHz laughter bursts)
        presence_samples = sosfilt(self.sos_presence, audio_data).astype(np.float32)
        _, presence_rms = fast_sliding_rms_tension(presence_samples, window_len, hop_len)

        n = len(times)
        speech_density = np.zeros(n, dtype=np.float32)
        laughter_curve = np.zeros(n, dtype=np.float32)

        # Baseline threshold for active speech
        voc_threshold = max(0.012, float(np.percentile(vocal_rms, 35)))

        for i in range(n):
            s_idx = i * hop_len
            e_idx = min(len(audio_data), s_idx + window_len)
            chunk = audio_data[s_idx:e_idx]
            if len(chunk) < 100:
                continue

            # Subframe energy ratio (fraction of 50ms frames inside the 1s window that contain speech)
            sub_len = int(self.sr * 0.05) # 50ms
            n_sub = len(chunk) // sub_len
            if n_sub > 0:
                active_subs = 0
                for s in range(n_sub):
                    sub_e = np.sqrt(np.mean(chunk[s*sub_len : (s+1)*sub_len]**2))
                    if sub_e > (voc_threshold * 0.6):
                        active_subs += 1
                speech_density[i] = float(active_subs) / float(n_sub)

            # Laughter burst signature: Rapid presence energy modulation with moderate overall energy
            pres = presence_rms[i] if i < len(presence_rms) else 0.0
            voc = vocal_rms[i] if i < len(vocal_rms) else 0.0
            if voc > 1e-4:
                ratio = pres / (voc + 1e-4)
                # Laughter has high presence-to-vocal ratio with bursty envelope
                if 0.4 < ratio < 2.5 and voc > (voc_threshold * 0.8):
                    laughter_curve[i] = min(3.0, ratio * (voc / voc_threshold))

        return times, speech_density, laughter_curve

    def _compute_onset_strength(self, rms_curve: np.ndarray) -> np.ndarray:
        """Compute onset strength from RMS energy curve (detects sudden energy increases)."""
        if len(rms_curve) < 2:
            return np.zeros(len(rms_curve), dtype=np.float32)

        # Half-wave rectified first derivative (only positive changes = onsets)
        delta = np.diff(rms_curve)
        onset = np.maximum(0, delta)

        # Pad to match original length
        onset = np.concatenate([np.zeros(1, dtype=np.float32), onset])

        # Normalize to z-score
        o_mean = np.mean(onset)
        o_std = np.std(onset)
        if o_std > 1e-6:
            onset = (onset - o_mean) / o_std

        return onset.astype(np.float32)

    def compute_energy_vad(
        self, audio_data: np.ndarray, frame_ms: int = 30
    ) -> np.ndarray:
        """Fast energy-based VAD for speech timing units."""
        frame_len = int(self.sr * (frame_ms / 1000.0))
        if len(audio_data) < frame_len:
            return np.zeros(1, dtype=np.float32)

        n_frames = len(audio_data) // frame_len
        frames = audio_data[: n_frames * frame_len].reshape((n_frames, frame_len))
        energies = np.sqrt(np.mean(frames**2, axis=1))

        # Dynamic speech threshold based on bottom 20% noise floor
        noise_floor = float(np.percentile(energies, 20))
        speech_thresh = max(0.015, noise_floor * 2.5)

        vad_prob = np.clip(
            (energies - noise_floor) / max(1e-5, speech_thresh - noise_floor), 0.0, 1.0
        )
        return vad_prob.astype(np.float32)



