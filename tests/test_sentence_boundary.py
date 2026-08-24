from channel_dna.core.models import ScanMarker
from channel_dna.core.sentence_boundary import SentenceBoundaryRefiner


def test_sentence_boundary_terminal_detection():
    refiner = SentenceBoundaryRefiner()

    assert refiner.is_sentence_terminal("했습니다.") is True
    assert refiner.is_sentence_terminal("좋다!") is True
    assert refiner.is_sentence_terminal("아니잖아?") is True
    assert refiner.is_sentence_terminal("했거든") is True
    assert refiner.is_sentence_terminal("센치해졌어") is True

    # Connectives should not be terminal
    assert refiner.is_sentence_terminal("그래서") is False
    assert refiner.is_sentence_terminal("하고") is False
    assert refiner.is_sentence_terminal("서사들") is False


def test_refine_marker_and_words_expansion():
    refiner = SentenceBoundaryRefiner(max_extension_sec=4.0)

    # Marker ends at 10.0s, but sentence ends at 11.5s with "좋습니다."
    m = ScanMarker(start_time=0.0, end_time=10.0, duration=10.0, peak_tension=3.0)
    words = [
        {"word": "안녕하세요", "start": 0.0, "end": 1.0},
        {"word": "오늘", "start": 1.2, "end": 2.0},
        {"word": "방송", "start": 9.0, "end": 9.8},
        {"word": "분위기", "start": 9.9, "end": 10.5},
        {"word": "정말", "start": 10.6, "end": 11.0},
        {"word": "좋습니다.", "start": 11.1, "end": 11.8},
    ]

    refined_m, final_words = refiner.refine_marker_and_words(m, words, slice_offset=0.0)

    assert refined_m.end_time >= 11.8
    assert len(final_words) == 6
    assert final_words[-1]["word"] == "좋습니다."
