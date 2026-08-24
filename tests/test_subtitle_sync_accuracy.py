"""Unit tests for subtitle sync and accuracy enhancements (Formant EQ, Kiwi Spacing, 2-frame Pre-lead)."""

import pytest
import numpy as np
from channel_dna.core.subtitle_preprocessor import SubtitleAudioPreprocessor
from channel_dna.core.subtitle_formatter import KoreanSentenceFormatter, LexiconPostProcessor


def test_formant_filter():
    preprocessor = SubtitleAudioPreprocessor(sr=16000)
    # Generate 1 second test audio with 50Hz sub-bass and 1000Hz speech tone
    t = np.linspace(0, 1.0, 16000, dtype=np.float32)
    audio = 0.5 * np.sin(2 * np.pi * 50 * t) + 0.5 * np.sin(2 * np.pi * 1000 * t)

    filtered = preprocessor.filter_vocal_band(audio)
    assert len(filtered) == len(audio)
    assert np.max(np.abs(filtered)) > 0


def test_kiwi_spacing_and_prelead_sync():
    formatter = KoreanSentenceFormatter(min_display_sec=0.80)
    words = [
        {"word": "아니진짜", "start": 1.00, "end": 1.40},
        {"word": "이게왜안돼", "start": 1.45, "end": 1.80},
    ]

    subs = formatter.format_words_to_subtitles(words)
    assert len(subs) == 1
    sub = subs[0]

    # 1. 2-frame Pre-lead (should start slightly before 1.00s, around 0.94s)
    assert sub.start_time <= 1.00

    # 2. Min display duration (should be at least 0.8s duration)
    assert (sub.end_time - sub.start_time) >= 0.80

    # 3. Kiwi automatic spacing
    assert " " in sub.text


def test_lexicon_meme_correction():
    proc = LexiconPostProcessor(custom_vocab="양망두, 댕케익")
    res = proc.correct_text("와 폼미쳣다 진짜 억가 레전드")
    assert "폼 미쳤다" in res
    assert "억까" in res
    assert "레전드" in res
