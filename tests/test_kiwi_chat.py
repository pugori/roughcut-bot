"""Unit tests for Kiwi Korean morphological meme analyzer in ChzzkChatEngine."""

import pytest
from channel_dna.core.chat_engine import KiwiChatAnalyzer, ChzzkChatEngine


def test_kiwi_chat_analyzer_sentiment():
    analyzer = KiwiChatAnalyzer.get_instance()

    score_plain = analyzer.analyze_message_sentiment("안녕하세요")
    assert score_plain >= 1.0

    score_laugh = analyzer.analyze_message_sentiment("아 진짜 너무 웃기네 ㅋㅋㅋㅋㅋ 빵터짐")
    assert score_laugh > score_plain

    score_hype = analyzer.analyze_message_sentiment("와 미쳤다 폼 미쳤다 레전드 ㄷㄷ 찢었다")
    assert score_hype > score_laugh

    score_outrage = analyzer.analyze_message_sentiment("아니 이건 진짜 억까 에반데")
    assert score_outrage > score_plain


def test_chat_velocity_curve_with_kiwi():
    engine = ChzzkChatEngine()
    chats = [
        {"playerMessageTime": 1000, "content": "안녕하세요 반갑습니다"},
        {"playerMessageTime": 5000, "content": "와 ㅋㅋㅋㅋ 레전드 ㄷㄷㄷ 억까 실화냐"},
        {"playerMessageTime": 5200, "content": "폼 미쳤다 찢었다 ㅋㅋㅋㅋ"},
        {"playerMessageTime": 5500, "content": "개웃기네 ㅋㅋㅋㅋㅋ"},
        {"playerMessageTime": 10000, "content": "수고하셨습니다"},
    ]

    curve = engine.compute_chat_velocity_curve(chats, duration_sec=15.0)
    assert len(curve) >= 14
    assert curve[5] > curve[1]
    assert curve[5] > curve[10]
