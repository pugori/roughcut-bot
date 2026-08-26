"""Graph Curve Pattern Similarity Engine for Channel DNA & VOD Highlight Matching.
Extracts build-up/climax/afterglow waveform motifs from edited YouTube videos and performs
Numba C-JIT accelerated sliding Pearson correlation & Cosine shape matching on raw VODs.
"""

from channel_dna.core.logger import get_logger

_logger = get_logger(__name__)


import numpy as np
from numba import njit

try:
    import channel_dna_native

    _HAS_RUST_NATIVE = True
except Exception:
    _HAS_RUST_NATIVE = False


@njit(fastmath=True)
def resample_1d_curve(curve: np.ndarray, target_len: int = 32) -> np.ndarray:
    """Resample 1D curve to fixed target length using linear interpolation and normalize to [0.0, 1.0]."""
    n_orig = len(curve)
    if n_orig == 0:
        return np.zeros(target_len, dtype=np.float32)
    if n_orig == 1:
        return np.full(target_len, curve[0], dtype=np.float32)

    resampled = np.zeros(target_len, dtype=np.float32)
    step = (n_orig - 1.0) / (target_len - 1.0)

    for i in range(target_len):
        pos = i * step
        idx_low = int(pos)
        idx_high = min(n_orig - 1, idx_low + 1)
        weight = pos - idx_low
        resampled[i] = curve[idx_low] * (1.0 - weight) + curve[idx_high] * weight

    # Min-Max Normalization to [0.0, 1.0]
    min_v = np.min(resampled)
    max_v = np.max(resampled)
    range_v = max_v - min_v

    if range_v > 1e-5:
        resampled = (resampled - min_v) / range_v
    else:
        resampled = np.zeros(target_len, dtype=np.float32)

    return resampled.astype(np.float32)


@njit(fastmath=True)
def fast_pearson_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """Numba C-JIT accelerated Pearson correlation coefficient (-1.0 to 1.0)."""
    n = len(x)
    if n != len(y) or n < 2:
        return 0.0

    sum_x = 0.0
    sum_y = 0.0
    for i in range(n):
        sum_x += x[i]
        sum_y += y[i]

    mean_x = sum_x / n
    mean_y = sum_y / n

    cov = 0.0
    var_x = 0.0
    var_y = 0.0

    for i in range(n):
        dx = x[i] - mean_x
        dy = y[i] - mean_y
        cov += dx * dy
        var_x += dx * dx
        var_y += dy * dy

    denom = np.sqrt(var_x * var_y)
    if denom > 1e-6:
        return cov / denom
    return 0.0


@njit(fastmath=True)
def fast_cosine_similarity(x: np.ndarray, y: np.ndarray) -> float:
    """Numba C-JIT Cosine similarity (0.0 to 1.0 for non-negative vectors)."""
    n = len(x)
    dot = 0.0
    norm_x = 0.0
    norm_y = 0.0
    for i in range(n):
        dot += x[i] * y[i]
        norm_x += x[i] * x[i]
        norm_y += y[i] * y[i]

    denom = np.sqrt(norm_x * norm_y)
    if denom > 1e-6:
        return dot / denom
    return 0.0


def compute_dtw_similarity(
    candidate_curve: np.ndarray, template_curve: np.ndarray
) -> float:
    """Computes non-linear Dynamic Time Warping (DTW) shape similarity (0.0 ~ 1.0) using FastDTW."""
    try:
        from fastdtw import fastdtw

        dist, path = fastdtw(
            candidate_curve, template_curve, dist=lambda a, b: abs(float(a) - float(b))
        )
        norm_dist = dist / max(1, len(path))
        # Convert distance to bounded similarity score
        sim = float(np.exp(-norm_dist * 2.5))
        return float(min(1.0, max(0.0, sim)))
    except Exception:
        return float(
            max(0.0, fast_pearson_correlation(candidate_curve, template_curve))
        )


@njit(fastmath=True)
def fast_sliding_motif_match(
    tensions: np.ndarray,
    times: np.ndarray,
    template: np.ndarray,
    window_frames: int,
    hop_frames: int,
    target_len: int = 32,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Numba C-JIT Sliding Pearson/Cosine graph shape pattern matching across continuous VOD timeline."""
    n_frames = len(tensions)
    if n_frames < window_frames:
        return (
            np.zeros(0, dtype=np.float32),
            np.zeros(0, dtype=np.float32),
            np.zeros(0, dtype=np.float32),
        )

    n_steps = (n_frames - window_frames) // hop_frames + 1
    match_times = np.zeros(n_steps, dtype=np.float32)
    match_sims = np.zeros(n_steps, dtype=np.float32)
    match_peaks = np.zeros(n_steps, dtype=np.float32)

    for i in range(n_steps):
        start_idx = i * hop_frames
        end_idx = start_idx + window_frames

        window_data = tensions[start_idx:end_idx]
        resampled_win = resample_1d_curve(window_data, target_len)

        # Compute Shape Similarity (Pearson r + Cosine blended)
        r = fast_pearson_correlation(resampled_win, template)
        cos_sim = fast_cosine_similarity(resampled_win, template)
        shape_score = max(0.0, r * 0.7 + cos_sim * 0.3)

        # Peak amplitude inside window
        peak_val = 0.0
        for j in range(start_idx, end_idx):
            peak_val = max(peak_val, tensions[j])

        center_t = (times[start_idx] + times[end_idx - 1]) * 0.5
        match_times[i] = center_t
        match_sims[i] = shape_score
        match_peaks[i] = peak_val

    return match_times, match_sims, match_peaks


class GraphEngine:
    def __init__(self, target_motif_len: int = 32):
        self.target_len = target_motif_len

    def get_default_motif_template(self) -> list[float]:
        """Default 3-stage Story Arc (Gentle Build-up -> High Climax Peak -> Resolving Afterglow)."""
        x = np.linspace(0, 1, self.target_len)
        buildup = np.exp(-((x - 0.55) ** 2) / (2 * 0.18**2))
        norm_template = (buildup - np.min(buildup)) / (
            np.max(buildup) - np.min(buildup)
        )
        return norm_template.astype(np.float32).tolist()

    def extract_motif_template(self, segment_curves: list[list[float]]) -> list[float]:
        """Extract average normalized highlight curve motif template from multiple video cuts."""
        if not segment_curves:
            return self.get_default_motif_template()

        resampled_list = []
        for curve in segment_curves:
            arr = np.array(curve, dtype=np.float32)
            if len(arr) >= 4 and np.max(arr) > 0.5:
                norm_c = resample_1d_curve(arr, self.target_len)
                resampled_list.append(norm_c)

        if len(resampled_list) < 2:
            return self.get_default_motif_template()

        stack = np.vstack(resampled_list)
        mean_curve = np.mean(stack, axis=0)

        min_v = np.min(mean_curve)
        max_v = np.max(mean_curve)
        if max_v - min_v > 1e-5:
            norm_motif = (mean_curve - min_v) / (max_v - min_v)
        else:
            norm_motif = np.array(self.get_default_motif_template(), dtype=np.float32)

        return norm_motif.astype(np.float32).tolist()

    def find_graph_pattern_matches(
        self,
        times: np.ndarray,
        tensions: np.ndarray,
        motif_template: list[float] | None = None,
        asl_sec: float = 8.3,
        rms_threshold: float = 1.75,
        min_shape_similarity: float = 0.60,
    ) -> list[tuple[float, float, float, float]]:
        """Find matching highlight episodes matching both intensity threshold and graph curve shape motif.
        Returns: List of (start_time, end_time, peak_tension, shape_similarity)
        """
        if len(tensions) < 10:
            return []

        template_arr = np.array(
            motif_template
            if motif_template is not None
            else self.get_default_motif_template(),
            dtype=np.float32,
        )
        if len(template_arr) != self.target_len:
            template_arr = resample_1d_curve(template_arr, self.target_len)

        if False:  # _HAS_RUST_NATIVE
            try:
                matches_rs = channel_dna_native.find_graph_pattern_matches_rs(
                    np.ascontiguousarray(times, dtype=np.float32),
                    np.ascontiguousarray(tensions, dtype=np.float32),
                    template_arr,
                    float(asl_sec),
                    float(rms_threshold),
                    float(min_shape_similarity),
                )
                if matches_rs:
                    return matches_rs
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)

        dt = float(times[1] - times[0]) if len(times) > 1 else 0.5
        fps_tension = 1.0 / max(1e-4, dt)

        scales = [max(6.0, asl_sec * 1.2), max(14.0, asl_sec * 2.5)]
        raw_candidates = []

        for win_sec in scales:
            win_frames = max(4, int(round(win_sec * fps_tension)))
            hop_frames = max(1, int(round(1.0 * fps_tension)))

            m_times, m_sims, m_peaks = fast_sliding_motif_match(
                tensions=tensions.astype(np.float32),
                times=times.astype(np.float32),
                template=template_arr,
                window_frames=win_frames,
                hop_frames=hop_frames,
                target_len=self.target_len,
            )

            half_win = win_sec * 0.5
            for idx_step, (t_center, sim, peak) in enumerate(
                zip(m_times, m_sims, m_peaks)
            ):
                # FastDTW non-linear refinement for elastic pacing / build-up
                dtw_sim = float(sim)
                if (peak >= (rms_threshold * 0.60)) and (sim < min_shape_similarity):
                    start_idx = idx_step * hop_frames
                    end_idx = min(len(tensions), start_idx + win_frames)
                    if end_idx - start_idx >= 4:
                        win_data = resample_1d_curve(
                            tensions[start_idx:end_idx], self.target_len
                        )
                        dtw_sim = max(
                            float(sim), compute_dtw_similarity(win_data, template_arr)
                        )

                final_sim = max(float(sim), dtw_sim)

                # Multi-criteria candidate admission:
                # 1. Standard: Meets target threshold and shape similarity (Linear or DTW)
                # 2. Narrative/Wit: High shape similarity with moderate energy
                # 3. Super Peak: Intense moment regardless of shape
                is_standard = (peak >= rms_threshold) and (
                    final_sim >= min_shape_similarity
                )
                is_narrative = (peak >= (rms_threshold * 0.65)) and (
                    final_sim >= max(0.50, min_shape_similarity * 0.85)
                )
                is_super_peak = peak >= (rms_threshold * 1.40)

                if is_standard or is_narrative or is_super_peak:
                    st = max(0.0, float(t_center - half_win))
                    et = float(t_center + half_win)
                    raw_candidates.append((st, et, float(peak), float(final_sim)))

        if not raw_candidates:
            return []

        raw_candidates.sort(key=lambda x: x[0])
        merged_episodes: list[tuple[float, float, float, float]] = []

        cur_st, cur_et, cur_pk, cur_sim = raw_candidates[0]

        for st, et, pk, sim in raw_candidates[1:]:
            if st <= cur_et + 5.0:
                cur_et = max(cur_et, et)
                cur_pk = max(cur_pk, pk)
                cur_sim = max(cur_sim, sim)
            else:
                dur = cur_et - cur_st
                if 5.0 <= dur <= 120.0:
                    merged_episodes.append((cur_st, cur_et, cur_pk, cur_sim))
                cur_st, cur_et, cur_pk, cur_sim = st, et, pk, sim

        dur = cur_et - cur_st
        if 5.0 <= dur <= 120.0:
            merged_episodes.append((cur_st, cur_et, cur_pk, cur_sim))

        return merged_episodes


# Module import JIT warm-up for zero first-run latency
def _warmup_numba_jit():
    try:
        dummy_arr = np.array([0.1, 0.5, 0.9, 0.3], dtype=np.float32)
        dummy_t = np.array([0.0, 1.0, 2.0, 3.0], dtype=np.float32)
        dummy_tpl = np.zeros(32, dtype=np.float32)
        resample_1d_curve(dummy_arr, 32)
        fast_pearson_correlation(dummy_tpl, dummy_tpl)
        fast_cosine_similarity(dummy_tpl, dummy_tpl)
        fast_sliding_motif_match(dummy_arr, dummy_t, dummy_tpl, 2, 1, 32)
    except Exception as e:
        _logger.debug("Silenced exception: %s", e)


_warmup_numba_jit()
