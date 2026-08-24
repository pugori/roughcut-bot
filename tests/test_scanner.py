import numpy as np
import soundfile as sf
from channel_dna.core.scanner import VODScanner
from channel_dna.core.models import ChannelProfile, ScanMarker


def test_scanner_markers_and_buffering(tmp_path):
    scanner = VODScanner()

    # Create 30s synthetic audio
    sr = 16000
    dur = 30.0
    t = np.linspace(0, dur, int(sr * dur))
    audio = 0.02 * np.random.randn(len(t))
    # Spike at 10s ~ 14s
    audio[int(10.0 * sr) : int(14.0 * sr)] += 0.8 * np.sin(2 * np.pi * 1800 * t[int(10.0 * sr) : int(14.0 * sr)])

    wav_file = tmp_path / "synthetic_vod.wav"
    sf.write(str(wav_file), audio, sr)

    profile = ChannelProfile(profile_id="test", channel_name="TestStreamer", highlight_rms_threshold=1.0)

    markers = scanner.scan(str(wav_file), profile, use_cache=False)

    assert len(markers) >= 1
    # Check buffering (-3s / +2s) around the 10s~14s event
    m = markers[0]
    assert m.start_time <= 10.0  # Buffer before
    assert m.end_time >= 14.0  # Buffer after
    assert m.duration >= 2.5
