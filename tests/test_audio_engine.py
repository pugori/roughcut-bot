import numpy as np
from channel_dna.core.audio_engine import AudioEngine


def test_audio_engine_bandpass_and_tension():
    engine = AudioEngine(sr=16000)

    # 5 seconds test signal: silence + 1500Hz sine wave (tension) + noise
    sr = 16000
    dur = 5.0
    t = np.linspace(0, dur, int(sr * dur))
    audio = 0.01 * np.random.randn(len(t))
    # Add strong 1500Hz tone at 2s ~ 4s
    audio[int(2.0 * sr) : int(4.0 * sr)] += 0.8 * np.sin(2 * np.pi * 1500 * t[int(2.0 * sr) : int(4.0 * sr)])

    times, tension = engine.compute_sliding_tension(audio)

    assert len(times) == len(tension)
    assert len(times) > 0

    # Tension in active tone region (2.0s ~ 4.0s) should be higher than background noise (0.0s ~ 1.5s)
    mask_active = (times >= 2.2) & (times <= 3.8)
    mask_silence = (times >= 0.1) & (times <= 1.5)

    assert np.mean(tension[mask_active]) > np.mean(tension[mask_silence])
