"""Unit tests for ruptures narrative chaptering and sectional quota highlight allocation."""

import pytest
import numpy as np
from channel_dna.core.scanner import detect_vod_chapters
from channel_dna.core.models import ChannelProfile


def test_detect_vod_chapters():
    # Simulate 3-hour VOD (21600 frames at 0.5s per frame = 10800s = 180 min)
    n_frames = 21600
    times = np.linspace(0, 10800, n_frames, dtype=np.float32)
    tension = np.zeros(n_frames, dtype=np.float32)
    tension[:5400] = 0.3 + 0.1 * np.random.randn(5400)
    tension[5400:16200] = 0.6 + 0.15 * np.random.randn(10800)
    tension[16200:] = 0.9 + 0.2 * np.random.randn(5400)
    tension = np.clip(tension, 0.0, 3.0)

    chapters = detect_vod_chapters(times, tension)
    assert len(chapters) >= 2
    assert chapters[0][0] == 0.0
    assert abs(chapters[-1][1] - 10800.0) < 1.0
    assert "[1부]" in chapters[0][2]


def test_narrative_quota_profile():
    prof = ChannelProfile(
        profile_id="test_solo",
        channel_name="test_solo",
        narrative_quota={"intro": 0.25, "body": 0.50, "outro": 0.25},
        speech_density_weight=0.45,
    )
    assert prof.narrative_quota["intro"] == 0.25
    assert prof.narrative_quota["body"] == 0.50
    assert prof.speech_density_weight == 0.45
