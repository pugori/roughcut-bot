"""Tests for Advanced Two-Track (Solo vs Collab) Classifier."""

import pytest
import numpy as np
from channel_dna.core.classifier import classify_youtube_video, classify_chzzk_vod
from channel_dna.core.models import SegmentData


def test_youtube_solo_videos():
    # 1. Obvious Solo titles
    assert classify_youtube_video(title="혼자서 해보는 솔로 랭크 챌린지")[0] == "solo"
    assert classify_youtube_video(title="[소통] 오늘 방송에서 썰풀기 & Q&A")[0] == "solo"
    assert classify_youtube_video(title="영도 보다가 빵터진 날 ㅋㅋㅋ")[0] == "solo"
    assert classify_youtube_video(title="혼술 먹방 브이로그")[0] == "solo"
    assert classify_youtube_video(title="자유랭 솔큐 1위 도전기")[0] == "solo"


def test_youtube_collab_videos():
    # 1. Collab with particles
    assert classify_youtube_video(title="우왁굳이랑 돝람쥐의 마크 생존기")[0] == "collab"
    assert classify_youtube_video(title="침착맨과 주호민의 무인도 탈출")[0] == "collab"
    assert classify_youtube_video(title="괴물쥐 x 랄로 x 파카 롤 3인큐")[0] == "collab"
    assert classify_youtube_video(title="김봉준 VS 감스트 스타 결승전")[0] == "collab"

    # 2. Collab with bracket keywords
    assert classify_youtube_video(title="[합방] 드디어 만났습니다ㅋㅋㅋ")[0] == "collab"
    assert classify_youtube_video(title="(초대석) 전설의 게스트 모셨습니다")[0] == "collab"
    assert classify_youtube_video(title="[내전] 스트리머 10인 자낳대 스크림")[0] == "collab"
    assert classify_youtube_video(title="이세돌 멤버들과 함께하는 갈틱폰")[0] == "collab"

    # 3. Collab with Description Links & Mentions
    desc_with_link = "함께해주신 분들:\n- 채널A: https://youtube.com/@streamerA\n- 채널B: https://chzzk.naver.com/live/12345"
    assert classify_youtube_video(title="오늘도 즐거운 하루", description=desc_with_link)[0] == "collab"

    # 4. Collab with Tags
    assert classify_youtube_video(title="치열한 경기", tags=["합방", "디스코드", "듀오"])[0] == "collab"


def test_youtube_collab_with_asl():
    # Fast conversational turn-taking cut pace (ASL < 2.6s) with title particle
    segs = [
        SegmentData(start_time=0.0, end_time=2.0, duration=2.0, rms_peak=1.0),
        SegmentData(start_time=2.0, end_time=3.8, duration=1.8, rms_peak=1.2),
        SegmentData(start_time=3.8, end_time=5.5, duration=1.7, rms_peak=1.1),
        SegmentData(start_time=5.5, end_time=7.6, duration=2.1, rms_peak=1.3),
        SegmentData(start_time=7.6, end_time=9.5, duration=1.9, rms_peak=1.0),
        SegmentData(start_time=9.5, end_time=11.2, duration=1.7, rms_peak=1.2),
    ]
    assert classify_youtube_video(title="철수랑 영희", avg_shot_length=1.9, segments=segs)[0] == "collab"


def test_chzzk_vod_collab_detection():
    # 1. Collab via title
    mode, conf, reason = classify_chzzk_vod(title="스트리머 합방 디코 내전 1일차")
    assert mode == "collab"
    assert conf >= 0.70
    assert "합방" in reason

    # 2. Collab via chat logs across stream
    chats = [
        {"content": "오늘 합방 레전드네요 ㅋㅋㅋ"},
        {"content": "디코 누구누구 들어왔나요?"},
        {"content": "게스트 목소리 진짜 좋다"},
        {"content": "통화 소리 좀 키워주세요"},
        {"content": "합방 너무 재밌다 ㅋㅋㅋ"},
        {"content": "디스코드 꿀잼"},
        {"content": "누구님이랑 같이 하니까 텐션 미침"},
        {"content": "합동방송 자주 해주세요"},
        {"content": "팀원들 합 짱이네"},
        {"content": "다인큐 가즈아"},
        {"content": "디코 소리 잘 들려요"},
        {"content": "합방 멤버 라인업 실화냐"},
    ]
    mode2, conf2, reason2 = classify_chzzk_vod(title="20260822_broadcast", chat_logs=chats)
    assert mode2 == "collab"
    assert "채팅창" in reason2


def test_chzzk_vod_solo_detection():
    # Solo with intro talking
    sr = 16000
    # Generate 5 minutes of synthetic audio with natural pauses (silence ratio > 40%)
    np.random.seed(42)
    audio = np.zeros(sr * 300, dtype=np.float32)
    # Speech in short bursts (1s speech, 2s silence)
    for i in range(0, len(audio), sr * 3):
        audio[i : i + sr] = np.random.randn(sr) * 0.1

    mode, conf, reason = classify_chzzk_vod(
        title="혼자서 조용히 하는 소통 및 노가리 방송",
        audio_samples=audio,
        sr=sr,
    )
    assert mode == "solo"
    assert "솔로" in reason
