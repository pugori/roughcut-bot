import numpy as np
from channel_dna.core.models import ScanMarker
from channel_dna.core.subtitle_preprocessor import SubtitleAudioPreprocessor
from channel_dna.core.subtitle_formatter import SubtitleItem, KoreanSentenceFormatter, LexiconPostProcessor
from channel_dna.core.subtitles import SubtitleEngine


def test_subtitle_preprocessor():
    pre = SubtitleAudioPreprocessor(sr=16000)
    audio = np.random.randn(16000 * 5).astype(np.float32) * 0.01

    # 1. AGC Normalization
    norm_audio = pre.apply_agc_normalization(audio)
    assert len(norm_audio) == len(audio)
    assert np.max(np.abs(norm_audio)) <= 1.0

    # 2. Vocal Bandpass
    filtered = pre.filter_vocal_band(audio)
    assert len(filtered) == len(audio)

    # 3. Pre-roll slice
    m = ScanMarker(start_time=2.0, end_time=4.0, duration=2.0, peak_tension=2.0)
    slice_audio, st, et = pre.extract_marker_slice_with_preroll(audio, m, pre_roll_sec=1.0)
    assert st == 1.0
    assert et == 5.0
    assert len(slice_audio) > 0


def test_lexicon_postprocessor():
    proc = LexiconPostProcessor(custom_vocab="독케익, 괴담읽기, 공포괴담")

    raw_text = "안녕하세요 독 케이크 님 오늘 괴담 읽기 방송 레 전드네요 억 가 하지 마세요"
    cleaned = proc.correct_text(raw_text)

    assert "독케익" in cleaned
    assert "괴담읽기" in cleaned
    assert "레전드" in cleaned
    assert "억까" in cleaned


def test_korean_sentence_formatter():
    formatter = KoreanSentenceFormatter(max_chars_per_line=15, max_lines_per_sub=2)
    words = [
        {"word": "\uc9c4\uc9dc", "start": 0.0, "end": 0.5},
        {"word": "\ub108\ubb34", "start": 0.6, "end": 1.0},
        {"word": "\ubb34\uc12d\uc2b5\ub2c8\ub2e4", "start": 1.1, "end": 1.8},
        {"word": "\uc5ec\ub7ec\ubd84", "start": 1.9, "end": 2.3},
        {"word": "\ub2e4\ub4e4", "start": 3.0, "end": 3.5},
        {"word": "\ub3c4\ub9dd\uce58\uc138\uc694", "start": 3.6, "end": 4.2},
    ]

    subs = formatter.format_words_to_subtitles(words, time_offset=10.0)
    assert len(subs) >= 2
    assert abs(subs[0].start_time - 10.0) <= 0.10
    assert "진짜" in subs[0].text


def test_subtitle_engine_export_srt(tmp_path):
    eng = SubtitleEngine()
    subs = [
        SubtitleItem(
            index=1, start_time=10.0, end_time=12.5, text="\uc9c4\uc9dc \ub108\ubb34 \ubb34\uc12d\uc2b5\ub2c8\ub2e4"
        ),
        SubtitleItem(index=2, start_time=13.0, end_time=15.2, text="\ub2e4\ub4e4 \ub3c4\ub9dd\uce58\uc138\uc694"),
    ]
    srt_out = tmp_path / "test.srt"
    res = eng.export_srt(subs, str(srt_out))
    assert res.exists()
    content = res.read_text(encoding="utf-8")
    assert "00:00:10,000 --> 00:00:12,500" in content
