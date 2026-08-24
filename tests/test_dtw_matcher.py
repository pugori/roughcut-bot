"""Unit tests for FastDTW non-linear waveform pattern matcher."""

import pytest
import numpy as np
from channel_dna.core.graph_engine import GraphEngine, compute_dtw_similarity


def test_compute_dtw_similarity():
    # 1. Exact match
    c1 = np.array([0.0, 0.2, 0.8, 1.0, 0.4, 0.0], dtype=np.float32)
    c2 = np.array([0.0, 0.2, 0.8, 1.0, 0.4, 0.0], dtype=np.float32)
    sim = compute_dtw_similarity(c1, c2)
    assert sim >= 0.95

    # 2. Time-warped / stretched curve (same story arc, slower climax)
    c_stretched = np.array([0.0, 0.1, 0.2, 0.4, 0.7, 0.9, 1.0, 0.8, 0.4, 0.1, 0.0], dtype=np.float32)
    sim_dtw = compute_dtw_similarity(c1, c_stretched)
    assert sim_dtw >= 0.60

    # 3. Completely inverted curve (anti-pattern)
    c_inverted = np.array([1.0, 0.8, 0.2, 0.0, 0.6, 1.0], dtype=np.float32)
    sim_inv = compute_dtw_similarity(c1, c_inverted)
    assert sim_dtw > sim_inv


def test_graph_engine_dtw_matching():
    engine = GraphEngine(target_motif_len=32)
    times = np.linspace(0, 60, 120, dtype=np.float32)
    tensions = np.zeros(120, dtype=np.float32)

    # Inject a realistic climax build-up around 20s ~ 40s (frames 40 ~ 80)
    for i in range(40, 80):
        tensions[i] = 1.8 * np.exp(-((i - 60)**2) / (2 * 10**2))

    matches = engine.find_graph_pattern_matches(
        times=times,
        tensions=tensions,
        asl_sec=5.0,
        rms_threshold=1.0,
        min_shape_similarity=0.45,
    )
    assert len(matches) >= 1
    st, et, peak, sim = matches[0]
    assert 5.0 <= st <= 25.0
    assert 35.0 <= et <= 55.0
    assert peak >= 1.0
    assert sim >= 0.45
