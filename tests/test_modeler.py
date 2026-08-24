from channel_dna.core.profiler import ChannelProfiler
from channel_dna.core.graph_engine import GraphEngine
from channel_dna.core.models import VideoMetadata, SegmentData
from channel_dna.core.db import DBManager
import numpy as np


def test_profiler_and_graph_engine(tmp_path):
    db = DBManager(tmp_path / "test.db")

    # Save dummy video analyses
    meta1 = VideoMetadata(
        video_id="v1", title="괴담 1편 레전드", duration=60.0, avg_shot_length=3.0, channel_name="StreamerA"
    )
    meta2 = VideoMetadata(
        video_id="v2", title="괴담 2편 공포", duration=80.0, avg_shot_length=4.0, channel_name="StreamerA"
    )
    segs = [
        SegmentData(video_id="v1", start_time=0.0, end_time=10.0, duration=10.0, rms_peak=2.5),
        SegmentData(video_id="v2", start_time=0.0, end_time=10.0, duration=10.0, rms_peak=1.8),
    ]
    db.save_video_analysis(meta1, segs[:1])
    db.save_video_analysis(meta2, segs[1:])

    profiler = ChannelProfiler(db)
    profile = profiler.derive_profile("StreamerA")

    assert profile.channel_name in ("StreamerA", "StreamerA_Solo")
    assert profile.sample_count == 2
    assert profile.avg_shot_length == 3.5
    assert profile.highlight_rms_threshold > 1.0
    assert profile.motif_template is not None
    assert len(profile.motif_template) == 32

    # GraphEngine curve matching test
    engine = GraphEngine()
    times = np.linspace(0, 100, 200)
    tensions = np.zeros(200, dtype=np.float32)
    # create a build-up climax peak at t=50s
    tensions[90:110] = np.array(engine.get_default_motif_template()[:20], dtype=np.float32) * 3.0

    matches = engine.find_graph_pattern_matches(
        times=times, tensions=tensions, motif_template=profile.motif_template, asl_sec=3.5, rms_threshold=1.5
    )
    assert len(matches) >= 1
