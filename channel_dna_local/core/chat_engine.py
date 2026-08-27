"""Chzzk VOD Fast Chat Fetcher and Velocity/Sentiment Curve Calculator."""

from channel_dna_local.core.logger import get_logger

_logger = get_logger(__name__)

import json
import urllib.request
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class ChatMoment:
    time_sec: float
    chat_count: int
    sentiment_score: float
    top_keywords: list[str]


# Keyword weights for streamer chat sentiment
SENTIMENT_WEIGHTS = {
    # Laugh / Dopamine
    "ㅋ": 1.8,
    "ㅎ": 1.2,
    "웃": 1.5,
    "dogcaketwerk": 2.0,  # Channel emote
    # Shock / Hype
    "ㄷ": 2.0,
    "ㅁㅊ": 2.5,
    "레전드": 3.0,
    "와": 2.0,
    "대박": 2.5,
    "미쳤다": 3.0,
    "미쳤": 2.8,
    "나이스": 2.2,
    "극락": 2.5,
    "찢었다": 3.0,
    "폼미쳤": 3.0,
    "?": 1.2,
    "!": 1.2,
    # Donation / Cheese
    "치즈": 3.5,
    "후원": 3.5,
    "미션": 3.0,
    # Horror / Suspense
    "ㄹㅇ": 1.8,
    "실화": 2.5,
    # Excitement
    "개쩐다": 2.5,
    "ㅇㅈ": 1.5,
    "인정": 1.5,
    # Surprise
    "ㄴㅇㄱ": 2.0,
    "헐": 2.0,
    "엥": 1.8,
    # Emotion / Sadness
    "ㅠㅠ": 1.5,
    "ㅜㅜ": 1.5,
    # Cheer
    "파이팅": 1.5,
    "가즈아": 2.0,
    "화이팅": 1.5,
    # Anger / Frustration / 억까
    "아니": 2.0,
    "억까": 3.0,
    "에반데": 2.5,
    "탈룰라": 2.5,
    "ㅡㅡ": 1.3,
    "ㅂㅅ": 2.0,
    # Gaming
    "gg": 2.0,
    "ㅈㅈ": 1.8,
    "킬": 1.5,
    "죽어": 1.8,
    # Consecutive Emote Burst
    "ㅋㅋㅋ": 2.5,
    "ㅎㅎㅎ": 2.0,
    "???": 2.0,
    "!!!": 2.0,
}


class KiwiChatAnalyzer:
    """High-speed C++ Korean Morphological Meme & Sentiment Analyzer using Kiwi."""

    _instance = None

    def __init__(self):
        self.kiwi = None
        try:
            from kiwipiepy import Kiwi

            self.kiwi = Kiwi(num_workers=2)
        except Exception as e:
            _logger.debug("Silenced exception: %s", e)

    @classmethod
    def get_instance(cls) -> "KiwiChatAnalyzer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def analyze_message_sentiment(self, text: str) -> float:
        """Returns emotional weight score based on Kiwi morphological parsing."""
        if not text:
            return 1.0

        weight = 1.0
        # Fast substring check
        for kw, w in SENTIMENT_WEIGHTS.items():
            if kw in text:
                weight += w

        # Kiwi morphological meme analysis
        if self.kiwi is not None:
            try:
                tokens = self.kiwi.tokenize(text)
                for token in tokens:
                    form = token.form
                    if form in ("억까", "레전드", "미치", "찢", "대박", "극락", "실화"):
                        weight += 2.0
                    elif form in ("ㅋㅋㅋ", "ㅎㅎㅎ", "ㄷㄷ", "헐", "와"):
                        weight += 1.5
                    elif token.tag in ("IC", "MAG") and form in (
                        "아니",
                        "진짜",
                        "너무",
                    ):
                        weight += 0.8
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)

        return weight


class ChzzkChatEngine:
    """Fetches high-speed full VOD chat logs from Chzzk and computes continuous chat velocity curve."""

    def __init__(self, user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"):
        self.headers = {"User-Agent": user_agent}
        from channel_dna_local.config import config

        self.cache_dir = config.default_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_vod_chat_logs(
        self, video_no: str, duration_sec: float, progress_cb=None
    ) -> list[dict[str, Any]]:
        """Paginates through Chzzk VOD chat API using playerMessageTime with disk caching."""
        cache_file = self.cache_dir / f"{video_no}_chats.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_chats = json.load(f)
                    if cached_chats:
                        if progress_cb:
                            progress_cb(
                                "ChatFetch",
                                1.0,
                                f"✓ 캐시된 채팅 로그 {len(cached_chats)}건 로드 완료.",
                            )
                        return cached_chats
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)

        all_chats = []
        player_msg_time = 0
        max_duration_ms = int(duration_sec * 1000)
        seen_chat_tokens = set()

        if progress_cb:
            progress_cb(
                "ChatFetch",
                0.1,
                f"치지직 VOD ({video_no}) 전체 채팅 로그 고속 수집 시작...",
            )

        while True:
            url = f"https://api.chzzk.naver.com/service/v1/videos/{video_no}/chats?playerMessageTime={player_msg_time}"
            req = urllib.request.Request(url, headers=self.headers)
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data.get("content", {})
                    chats = content.get("videoChats", [])
                    if not chats:
                        break

                    new_added = 0
                    for c in chats:
                        t = c.get("playerMessageTime", 0)
                        uid = c.get("userIdHash", "")
                        token = f"{t}_{uid}_{c.get('content', '')[:10]}"
                        if token not in seen_chat_tokens:
                            seen_chat_tokens.add(token)
                            all_chats.append(c)
                            new_added += 1

                    last_time = chats[-1].get("playerMessageTime", 0)
                    if last_time <= player_msg_time or new_added == 0:
                        player_msg_time += 60000  # Jump forward 1 min if stuck
                    else:
                        player_msg_time = last_time

                    if (
                        max_duration_ms > 0
                        and progress_cb
                        and len(all_chats) % 800 == 0
                    ):
                        pct = min(0.95, (player_msg_time / max_duration_ms) * 0.9)
                        progress_cb(
                            "ChatFetch",
                            pct,
                            f"채팅 수집 중: {len(all_chats)}건 (시간대: {int(player_msg_time / 1000)}초 / {int(duration_sec)}초)...",
                        )

                    if max_duration_ms > 0 and player_msg_time >= max_duration_ms:
                        break

            except Exception:
                break

        # Save to disk cache
        if all_chats:
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(all_chats, f, ensure_ascii=False)
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)

        if progress_cb:
            progress_cb(
                "ChatFetch",
                1.0,
                f"✓ 치지직 VOD 채팅 총 {len(all_chats)}건 수집 및 캐싱 완료.",
            )

        return all_chats

    def compute_chat_velocity_curve(
        self,
        chats: list[dict[str, Any]],
        duration_sec: float,
        bin_size_sec: float = 1.0,
    ) -> np.ndarray:
        """Builds second-by-second (1Hz) chat velocity and sentiment multiplier curve."""
        total_bins = int(np.ceil(duration_sec / bin_size_sec)) + 1
        raw_counts = np.zeros(total_bins, dtype=np.float32)
        sentiment_scores = np.zeros(total_bins, dtype=np.float32)

        kiwi_analyzer = KiwiChatAnalyzer.get_instance()
        for c in chats:
            t_sec = float(c.get("playerMessageTime", 0)) / 1000.0
            idx = int(t_sec / bin_size_sec)
            if 0 <= idx < total_bins:
                raw_counts[idx] += 1.0
                text = str(c.get("content", "")).strip()
                extras = str(c.get("extras", "")).strip()
                combined = f"{text} {extras}".strip()

                weight = kiwi_analyzer.analyze_message_sentiment(combined)
                sentiment_scores[idx] += weight

        # Consecutive message burst detection
        sentiment_scores[raw_counts > 10] *= 1.5

        # Smooth with Gaussian/Moving Average window (5-second smoothing)
        window = int(5.0 / bin_size_sec)
        if window > 1 and total_bins > window:
            kernel = np.hanning(window)
            kernel /= kernel.sum()
            smooth_curve = np.convolve(sentiment_scores, kernel, mode="same")
        else:
            smooth_curve = sentiment_scores

        # Z-score thresholding for better burst peak detection
        mean_val = np.mean(smooth_curve)
        std_val = np.std(smooth_curve)
        if std_val > 0:
            z_scores = (smooth_curve - mean_val) / std_val
            smooth_curve[z_scores > 2.0] *= 1.2

        # Normalize 0.0 ~ 3.0 scale
        if np.max(smooth_curve) > 0:
            norm_curve = (
                smooth_curve / np.percentile(smooth_curve[smooth_curve > 0], 90)
                if np.any(smooth_curve > 0)
                else smooth_curve
            )
        else:
            norm_curve = smooth_curve

        return norm_curve[: int(duration_sec)]

