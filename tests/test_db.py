from channel_dna.core.db import DBManager
from channel_dna.core.models import VideoMetadata, SegmentData, ChannelProfile


def test_db_init_and_profile_crud(tmp_path):
    db_file = tmp_path / "test.db"
    db = DBManager(db_file)

    profile = ChannelProfile(
        profile_id="p1",
        channel_name="TestChannel",
        sample_count=3,
        avg_shot_length=2.5,
        tension_interval=35.0,
        silence_tolerance=0.7,
        highlight_rms_threshold=1.5,
        hook_duration=10.0,
        youtube_url="https://youtube.com/@test",
        chzzk_url="https://chzzk.naver.com/test_id",
    )
    db.save_profile(profile)

    loaded = db.get_profile("TestChannel")
    assert loaded is not None
    assert loaded.channel_name == "TestChannel"
    assert loaded.avg_shot_length == 2.5
    assert loaded.highlight_rms_threshold == 1.5
    assert loaded.youtube_url == "https://youtube.com/@test"
    assert loaded.chzzk_url == "https://chzzk.naver.com/test_id"

    # Test update_channel_urls
    db.update_channel_urls("TestChannel", chzzk_url="https://chzzk.naver.com/new_id")
    loaded2 = db.get_profile("TestChannel")
    assert loaded2.youtube_url == "https://youtube.com/@test"
    assert loaded2.chzzk_url == "https://chzzk.naver.com/new_id"

    all_profiles = db.get_all_profiles()
    assert len(all_profiles) == 1


def test_db_video_and_segments(tmp_path):
    db_file = tmp_path / "test.db"
    db = DBManager(db_file)

    meta = VideoMetadata(
        video_id="vid123", title="Test Video", duration=120.0, avg_shot_length=3.0, channel_name="TestChannel"
    )
    segments = [
        SegmentData(video_id="vid123", start_time=0.0, end_time=5.0, duration=5.0, rms_peak=1.8, transcript="Hello"),
        SegmentData(video_id="vid123", start_time=5.0, end_time=10.0, duration=5.0, rms_peak=0.5, transcript="World"),
    ]

    db.save_video_analysis(meta, segments)

    videos = db.get_videos_by_channel("TestChannel")
    assert len(videos) == 1
    assert videos[0].video_id == "vid123"

    loaded_segs = db.get_segments_by_video("vid123")
    assert len(loaded_segs) == 2
    assert loaded_segs[0].transcript == "Hello"
