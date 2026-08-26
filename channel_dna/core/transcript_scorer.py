"""Transcript-based Semantic Highlight & Discourse Humor Scorer for Live Streams.
Analyzes speech transcriptions for discourse markers, conversational wit, narrative punchlines,
and emotional escalation patterns to score highlight probability even during quiet spoken dialogue.
"""

import re
from typing import Any

import numpy as np

# High-value streamer discourse markers & humor cues
HUMOR_DISCOURSE_PATTERNS = [
    # 1. 억울함 / 항변 / 티키타카
    (r"(아\s*니|아니\s*근데|아니\s*진짜|아니\s*내가|아니\s*그게)", 1.4),
    (r"(내가\s*지지|내가\s*이겼|내가\s*졌다|내가\s*맞잖아)", 1.5),
    (r"(아\s*아니야|아닌가|아\s*그런가|그런가요)", 1.3),
    (r"(대체\s*무슨|무슨\s*말을|이게\s*무슨|뭐라고\s*하는)", 1.5),
    (r"(어떻게\s*사|어떻게\s*해|어떡하지|어쩌라고)", 1.4),
    (r"(왜\s*이래|왜\s*저래|왜\s*그러지|왜\s*그래)", 1.3),
    (r"(말이\s*돼|말이\s*안\s*돼|말이\s*되냐)", 1.5),
    (r"(잠깐만|잠시만|기다려봐|잠깐\s*타임)", 1.2),
    # 2. 감탄 / 충격 / 반전 펀치라인
    (r"(레전드|미쳤다|폼\s*미쳤다|실화냐|실화임)", 1.6),
    (r"(극락|나이스|클러치|개이득|개손해|짜쳐|짜치네|맛도리)", 1.5),
    (r"(억까|억까야|억까네|억까\s*지리네)", 1.6),
    (r"(어\?|뭐\?|엥\?|헐|와|대박|오호)", 1.2),
    (r"(안녕히\s*계세요|수고하셨습니다|방종|여기까지)", 1.4),
    (r"(안\s*돼|제발|살려줘|죽었다|끝났다|망했다)", 1.5),
    # 3. 질문 및 반문 (시청자/동료와의 소통 활성화)
    (r"(\?{1,3}|냐\?|요\?|까\?|죠\?)", 1.15),
    # 4. 반복 자음/이모트 패턴 (연속 ㅋ, ㅎ, ?, !, ㄷ 등)
    (r"([ㅋㅎㄷㅠㅜ]{3,})", 1.3),
    # 5. 게임 특화 리액션 (킬, 사망, 승리 관련)
    (r"(잡았다|죽었|살았|컷|나이스\s*샷|캐리|버스|트롤|갱|오더|궁|피해|막아|빼)", 1.4),
    # 6. 감정 폭발 / 큰소리 (대문자 반복, 느낌표 연속)
    (r"(!{2,}|\?{2,}|!\?|\?!)", 1.25),
]


class TranscriptSemanticScorer:
    """Scores speech transcript lines for narrative importance and conversational humor."""

    def __init__(self, custom_keywords: list[str] | None = None):
        self.patterns = list(HUMOR_DISCOURSE_PATTERNS)
        if custom_keywords:
            for kw in custom_keywords:
                kw = kw.strip()
                if len(kw) >= 2:
                    self.patterns.append((re.escape(kw), 1.5))

    def score_sentence(self, text: str) -> float:
        """Computes semantic score (1.0 = baseline, up to 3.0 for intense discourse/humor)."""
        if not text:
            return 1.0

        cleaned = text.strip()
        base_score = 1.0

        for pattern, weight in self.patterns:
            if re.search(pattern, cleaned, flags=re.IGNORECASE):
                base_score *= weight

        # Detection for consecutive repeated characters (e.g. ㅋㅋㅋㅋ)
        # Score proportional to repetition count
        for m in re.finditer(r"([ㅋㅎㄷㅠㅜ])\1{2,}", cleaned):
            length = len(m.group(0))
            base_score *= 1.0 + (length * 0.02)

        # Mixed exclamation/question marks (뭐?! 왜?!)
        if re.search(r"(!\?|\?!)", cleaned):
            base_score *= 1.2

        # Dialogue speed/density detector: multiple sentences in a short time
        # Boost if there are multiple short phrases separated by punctuation
        phrases = [p for p in re.split(r"[.!?]+", cleaned) if p.strip()]
        if len(phrases) >= 3 and len(cleaned) < 50:
            base_score *= 1.15

        # Bonus for fast/dense dialogue (length > 8 chars within a punchy line)
        if 8 <= len(cleaned) <= 35:
            base_score *= 1.1

        return min(3.5, base_score)

    def generate_timeline_score_curve(
        self,
        transcript_segments: list[dict[str, Any]],
        times: np.ndarray,
        base_boost: float = 0.35,
    ) -> np.ndarray:
        """Converts timestamped transcript segments into a continuous timeline multiplier curve."""
        n_times = len(times)
        if n_times == 0 or not transcript_segments:
            return np.ones(n_times, dtype=np.float32)

        curve = np.ones(n_times, dtype=np.float32)

        for seg in transcript_segments:
            st = float(seg.get("start", 0.0))
            et = float(seg.get("end", 0.0))
            text = str(seg.get("text", ""))

            score = self.score_sentence(text)
            if score > 1.05:
                center = (st + et) * 0.5
                radius = max(2.5, (et - st) * 0.7)

                mask = (times >= (st - 1.5)) & (times <= (et + 1.5))
                if np.any(mask):
                    dt = times[mask] - center
                    weights = np.exp(-(dt**2) / (2 * (radius**2)))
                    boost = 1.0 + (score - 1.0) * base_boost
                    curve[mask] = np.maximum(curve[mask], 1.0 + (boost - 1.0) * weights)

        return curve.astype(np.float32)
