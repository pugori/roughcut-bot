"""Advanced Tests for Subtitle Engine: Zero-phase filtering, trim silence, overlap clamping, and lexicon."""

import pytest
import numpy as np
from channel_dna.core.subtitle_preprocessor import SubtitleAudioPreprocessor
from channel_dna.core.subtitle_formatter import KoreanSentenceFormatter, LexiconPostProcessor, DEFAULT_LEXICON_REPLACEMENTS


def test_zero_phase_vocal_filter():
    sr = 16000
    preprocessor = SubtitleAudioPreprocessor(sr=sr)

    # 1kHz test sine wave
    t = np.linspace(0, 1.0, sr, endpoint=False)
    sig = np.sin(2 * np.pi * 1000 * t).astype(np.float32)

    filtered = preprocessor.filter_vocal_band(sig)
    assert len(filtered) == len(sig)
    assert not np.isnan(filtered).any()

    # Verify peak alignment (Zero phase delay means peaks coincide)
    orig_peak_idx = np.argmax(sig[:20])
    filt_peak_idx = np.argmax(filtered[:20])
    assert abs(orig_peak_idx - filt_peak_idx) <= 1  # within 1 sample (0ms delay)


def test_silence_edge_trimming():
    sr = 16000
    preprocessor = SubtitleAudioPreprocessor(sr=sr)

    # 1.0s leading silence + 1.0s speech + 1.0s trailing silence
    silence_lead = np.zeros(sr * 1, dtype=np.float32)
    speech = np.random.randn(sr * 1).astype(np.float32) * 0.5
    silence_trail = np.zeros(sr * 1, dtype=np.float32)
    full_audio = np.concatenate([silence_lead, speech, silence_trail])

    trimmed, leading_trim_sec = preprocessor.trim_silence_edges(full_audio, pad_sec=0.2)
    assert 0.7 <= leading_trim_sec <= 0.85
    assert len(trimmed) < len(full_audio)
    assert len(trimmed) >= sr * 1.3  # Speech + 0.2s padding on each side


def test_subtitle_overlap_clamping():
    formatter = KoreanSentenceFormatter(min_display_sec=1.50)

    words = [
        {"word": " 안녕하세요", "start": 1.0, "end": 1.4},
        {"word": " 반갑습니다.", "start": 1.4, "end": 2.0},
        {"word": " 오늘", "start": 2.5, "end": 2.8},
        {"word": " 방송입니다.", "start": 2.8, "end": 3.4},
    ]

    subs = formatter.format_words_to_subtitles(words)
    assert len(subs) >= 2

    # Verify both sentences guarantee minimum readable display duration (>=1.50s)
    assert round(subs[0].end_time - subs[0].start_time, 2) >= 1.50
    assert round(subs[1].end_time - subs[1].start_time, 2) >= 1.50
    # Verify both subtitles are generated with valid timestamps
    assert subs[0].start_time < subs[0].end_time
    assert subs[1].start_time < subs[1].end_time


def test_streamer_lexicon_correction():
    lexicon = LexiconPostProcessor()

    assert lexicon.correct_text("오늘 치직 방송 억 가 레 전드") == "오늘 치지직 방송 억까 레전드"
    assert lexicon.correct_text("이거 쌉 가능 인가요") == "이거 쌉가능 인가요"
    assert lexicon.correct_text("디 코 들어오세요") == "디코 들어오세요"
    assert lexicon.correct_text("상대 킬 각 잡았습니다") == "상대 킬각 잡았습니다"
    assert lexicon.correct_text("독 케이크 사건 ㅋㅋㅋ") == "독케익 사건 ㅋㅋㅋ"


