"""Audio Preprocessor for Subtitles: Wideband Speech Conditioning, AGC Normalization, and Safe Margin Trimming."""

import numpy as np
from scipy.signal import butter, sosfiltfilt

from channel_dna_local.core.models import ScanMarker


class SubtitleAudioPreprocessor:
    """Preprocesses raw VOD audio before Whisper STT with wideband 80Hz~7500Hz vocal preservation and intelligent AGC."""

    def __init__(self, sr: int = 16000):
        self.sr = sr
        # Wideband speech filter (80Hz ~ 7500Hz) preserving full vocal clarity, sibilants, and laughter harmonics
        self.sos_vocal = butter(2, [80, 7500], btype="band", fs=sr, output="sos")

    def apply_agc_normalization(
        self, audio: np.ndarray, target_peak: float = 0.90
    ) -> np.ndarray:
        """Peak-aware dynamic range AGC normalization:
        Boosts quiet speech cleanly without introducing harmonic distortion to Whisper Mel Spectrograms.
        """
        if len(audio) == 0:
            return audio

        max_val = float(np.max(np.abs(audio)))
        if max_val < 1e-5:
            return audio

        rms = float(np.sqrt(np.mean(audio**2)))
        target_rms = 0.09

        if rms > 1e-4:
            gain = min(10.0, target_rms / rms)
            amplified = audio * gain
            peak = float(np.max(np.abs(amplified)))
            if peak > target_peak:
                amplified = amplified * (target_peak / peak)
            return amplified.astype(np.float32)

        return (audio * (target_peak / max_val)).astype(np.float32)

    def filter_vocal_band(self, audio: np.ndarray) -> np.ndarray:
        """Applies wideband 80Hz~7500Hz zero-phase filtering to remove low rumble and ultrasonic artifacts."""
        if len(audio) < 100:
            return audio
        try:
            filtered = sosfiltfilt(self.sos_vocal, audio)
        except Exception:
            filtered = audio
        return filtered.astype(np.float32)

    def trim_silence_edges(
        self, audio: np.ndarray, threshold_ratio: float = 0.015, pad_sec: float = 0.35
    ) -> tuple[np.ndarray, float]:
        """Safely trims dead silence from outer edges with generous 350ms padding to protect word onsets."""
        if len(audio) < int(self.sr * 0.5):
            return audio, 0.0

        abs_audio = np.abs(audio)
        peak = float(np.max(abs_audio))
        if peak < 1e-4:
            return audio, 0.0

        thresh = peak * threshold_ratio
        active_indices = np.where(abs_audio > thresh)[0]
        if len(active_indices) == 0:
            return audio, 0.0

        pad_samples = int(pad_sec * self.sr)
        start_idx = max(0, active_indices[0] - pad_samples)
        end_idx = min(len(audio), active_indices[-1] + pad_samples)

        leading_sec = start_idx / self.sr
        return audio[start_idx:end_idx].astype(np.float32), leading_sec

    def preprocess_slice(self, raw_slice: np.ndarray) -> np.ndarray:
        """Applies wideband conditioning and AGC normalization to raw audio slice."""
        if len(raw_slice) == 0:
            return raw_slice
        processed = self.filter_vocal_band(raw_slice)
        return self.apply_agc_normalization(processed)

    def extract_marker_slice_with_preroll(
        self,
        full_audio: np.ndarray,
        marker: ScanMarker,
        pre_roll_sec: float = 1.5,
        post_roll_sec: float = 1.5,
    ) -> tuple[np.ndarray, float, float]:
        """Extracts audio slice with generous pre-roll and post-roll margins."""
        total_sec = len(full_audio) / self.sr
        slice_start_sec = max(0.0, marker.start_time - pre_roll_sec)
        slice_end_sec = min(total_sec, marker.end_time + post_roll_sec)

        start_samp = int(slice_start_sec * self.sr)
        end_samp = int(slice_end_sec * self.sr)

        raw_slice = full_audio[start_samp:end_samp]
        processed_slice = self.preprocess_slice(raw_slice)
        return processed_slice, slice_start_sec, slice_end_sec

