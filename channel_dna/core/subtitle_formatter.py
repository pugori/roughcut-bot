"""Korean Subtitle Formatter & Lexicon Post-Processor.
Formats raw Whisper token segments into readable Korean variety-show sentences with Kiwi NLP,
guarantees minimum readability duration, and supports multi-layer overlapping dialogue.
"""

from channel_dna.core.logger import get_logger

_logger = get_logger(__name__)

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class SubtitleItem:
    index: int
    start_time: float
    end_time: float
    text: str

    @property
    def start_timecode(self) -> str:
        h = int(self.start_time // 3600)
        m = int((self.start_time % 3600) // 60)
        s = int(self.start_time % 60)
        ms = int(round((self.start_time - int(self.start_time)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @property
    def end_timecode(self) -> str:
        h = int(self.end_time // 3600)
        m = int((self.end_time % 3600) // 60)
        s = int(self.end_time % 60)
        ms = int(round((self.end_time - int(self.end_time)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# Common Twitch/Chzzk/YouTube gaming meme & slang normalization dictionary
DEFAULT_LEXICON_REPLACEMENTS = {
    r"독\s*케이크": "독케익",
    r"도케익": "독케익",
    r"치\s*직": "치지직",
    r"치\s*지\s*직": "치지직",
    r"치즈\s*후원": "치즈후원",
    r"억\s*가": "억까",
    r"억\s*까": "억까",
    r"억\s*빠": "억빠",
    r"극\s*락": "극락",
    r"나\s*락": "나락",
    r"나\s*이스": "나이스",
    r"레\s*전드": "레전드",
    r"영\s*도": "영도",
    r"영상\s*도네": "영도",
    r"투\s*네": "투네",
    r"트\s*윕": "트윕",
    r"디\s*코": "디코",
    r"디\s*스\s*코\s*드": "디스코드",
    r"방\s*송\s*각": "방송각",
    r"개\s*추": "개추",
    r"비\s*추": "비추",
    r"짜\s*쳐": "짜쳐",
    r"짜\s*치네": "짜치네",
    r"맛\s*도리": "맛도리",
    r"클\s*러치": "클러치",
    r"어\s*그로": "어그로",
    r"도\s*파민": "도파민",
    r"저\s*챗": "저챗",
    r"저스트\s*채팅": "저챗",
    r"방\s*종": "방종",
    r"방\s*제": "방제",
    r"쌉\s*가능": "쌉가능",
    r"쌉\s*파서블": "쌉가능",
    r"개\s*이득": "개이득",
    r"개\s*손해": "개손해",
    r"실\s*화냐": "실화냐",
    r"폼\s*미쳤다": "폼 미쳤다",
    r"폼\s*미쳣다": "폼 미쳤다",
    r"킬\s*각": "킬각",
    r"딜\s*각": "딜각",
    r"막\s*타": "막타",
    r"너\s*프": "너프",
    r"버\s*프": "버프",
    r"뇌\s*절": "뇌절",
    r"한\s*타": "한타",
    r"캐\s*리": "캐리",
    r"가\s*즈\s*아": "가즈아",
    r"가\s*자": "가자",
    r"헤\s*드\s*샷": "헤드샷",
    r"에\s*이\s*스": "에이스",
    r"존\s*버": "존버",
    r"빡\s*겜": "빡겜",
    r"즐\s*겜": "즐겜",
    r"티\s*어": "티어",
    r"리\s*액션": "리액션",
    r"초\s*대석": "초대석",
    r"합\s*방": "합방",
}


class LexiconPostProcessor:
    """Corrects common streamer slang, memes, and custom channel vocabulary."""

    def __init__(self, custom_vocab: str = ""):
        self.replacements = dict(DEFAULT_LEXICON_REPLACEMENTS)
        if custom_vocab:
            for term in custom_vocab.split(","):
                term = term.strip()
                if len(term) >= 2:
                    spaced_pattern = r"\s*".join(re.escape(c) for c in term)
                    self.replacements[spaced_pattern] = term

    def correct_text(self, text: str) -> str:
        """Applies regex dictionary correction."""
        cleaned = text
        for pattern, replacement in self.replacements.items():
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        return cleaned.strip()


class KoreanSentenceFormatter:
    """Combines fragmented word-level tokens into natural complete Korean sentences with Kiwi NLP,
    asymmetric cognitive headroom (-80ms lead-in, +200ms lead-out), and adaptive syllable-scaled reading durations.
    """

    _kiwi = None

    def __init__(
        self,
        max_chars_per_line: int = 18,
        max_lines_per_sub: int = 2,
        min_display_sec: float | None = None,
        max_display_sec: float = 4.50,
    ):
        self.max_chars = max_chars_per_line
        self.max_lines = max_lines_per_sub
        self.min_dur = min_display_sec
        self.max_dur = max_display_sec

    @classmethod
    def _get_kiwi(cls):
        if cls._kiwi is None:
            try:
                from kiwipiepy import Kiwi
                cls._kiwi = Kiwi(num_workers=1)
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)
        return cls._kiwi

    def format_words_to_subtitles(
        self,
        words: list[dict[str, Any]],
        time_offset: float = 0.0,
        lexicon_processor: LexiconPostProcessor | None = None,
    ) -> list[SubtitleItem]:
        """Groups word tokens into natural complete Korean sentences with smart editor headroom."""
        if not words:
            return []

        kiwi = self._get_kiwi()
        if not kiwi:
            return self._format_words_fallback(words, time_offset, lexicon_processor)

        # 1. Reconstruct text and build char-to-word index mapping
        full_text = ""
        char_to_word = []
        for w_idx, w in enumerate(words):
            w_str = str(w.get("word", ""))
            for _ in w_str:
                char_to_word.append(w_idx)
            full_text += w_str

        if not full_text.strip():
            return []

        # 2. Extract grammatical Korean sentences using Kiwi NLP
        kiwi_sents = kiwi.split_into_sents(full_text)
        subtitles: list[SubtitleItem] = []

        for s in kiwi_sents:
            s_text = s.text.strip()
            if not s_text or len(s_text) < 1:
                continue

            s_char_st = max(0, min(len(char_to_word) - 1, s.start))
            s_char_et = max(0, min(len(char_to_word) - 1, s.end - 1))

            w_st_idx = char_to_word[s_char_st]
            w_et_idx = char_to_word[s_char_et]

            # 3-frame pre-lead (-80ms early popup for perceptual reading sync)
            w_st = max(0.0, float(words[w_st_idx].get("start", 0.0)) + time_offset - 0.08)
            w_et = float(words[w_et_idx].get("end", 0.0)) + time_offset

            # Kiwi auto-spacing and lexicon correction
            try:
                s_text = kiwi.space(s_text)
            except Exception:
                pass

            if lexicon_processor:
                s_text = lexicon_processor.correct_text(s_text)

            s_text = self._clean_repetitive_stutter(s_text)
            if not s_text.strip():
                continue

            # Adaptive syllable-scaled reading headroom:
            # - Explicit min_dur override if specified
            # - Otherwise adaptive: 1~3 chars (0.60s), 4~8 chars (1.10s), 9~15 chars (1.60s), >15 chars (2.20s)
            if self.min_dur is not None:
                target_min_dur = self.min_dur
            else:
                clean_char_len = len(re.sub(r"[^\w]", "", s_text))
                if clean_char_len <= 3:
                    target_min_dur = 0.60
                elif clean_char_len <= 8:
                    target_min_dur = 1.10
                elif clean_char_len <= 15:
                    target_min_dur = 1.60
                else:
                    target_min_dur = min(self.max_dur, max(2.20, clean_char_len * 0.08))

            # Speech-Strict + Lead-Out (+200ms) bounded by target_min_dur and max_dur
            sub_end = max(w_st + target_min_dur, w_et + 0.20)
            final_end = min(w_st + self.max_dur, sub_end)

            subtitles.append(
                SubtitleItem(
                    index=len(subtitles) + 1,
                    start_time=round(w_st, 2),
                    end_time=round(final_end, 2),
                    text=self._wrap_lines(s_text),
                )
            )

        return subtitles

    def _format_words_fallback(
        self,
        words: list[dict[str, Any]],
        time_offset: float,
        lexicon_processor: LexiconPostProcessor | None,
    ) -> list[SubtitleItem]:
        subtitles: list[SubtitleItem] = []
        cur_words: list[str] = []
        cur_st = max(0.0, float(words[0].get("start", 0.0)) + time_offset - 0.08)
        prev_et = float(words[0].get("end", 0.0)) + time_offset

        for w in words:
            w_text = str(w.get("word", "")).strip()
            if not w_text:
                continue
            w_st = max(0.0, float(w.get("start", 0.0)) + time_offset - 0.08)
            w_et = float(w.get("end", 0.0)) + time_offset
            gap = w_st - prev_et
            line_len = sum(len(x) + 1 for x in cur_words)

            if (gap > 0.6 or line_len >= 22) and cur_words:
                text_block = " ".join(cur_words)
                if lexicon_processor:
                    text_block = lexicon_processor.correct_text(text_block)
                text_block = self._clean_repetitive_stutter(text_block)
                clean_len = len(re.sub(r"[^\w]", "", text_block))
                target_min = 0.60 if clean_len <= 3 else (1.10 if clean_len <= 8 else 1.60)
                sub_end = max(cur_st + target_min, prev_et + 0.20)
                subtitles.append(
                    SubtitleItem(
                        index=len(subtitles) + 1,
                        start_time=round(cur_st, 2),
                        end_time=round(min(cur_st + self.max_dur, sub_end), 2),
                        text=self._wrap_lines(text_block),
                    )
                )
                cur_words = [w_text]
                cur_st = w_st
            else:
                cur_words.append(w_text)
            prev_et = w_et

        if cur_words:
            text_block = " ".join(cur_words)
            if lexicon_processor:
                text_block = lexicon_processor.correct_text(text_block)
            text_block = self._clean_repetitive_stutter(text_block)
            clean_len = len(re.sub(r"[^\w]", "", text_block))
            target_min = 0.60 if clean_len <= 3 else (1.10 if clean_len <= 8 else 1.60)
            sub_end = max(cur_st + target_min, prev_et + 0.20)
            subtitles.append(
                SubtitleItem(
                    index=len(subtitles) + 1,
                    start_time=round(cur_st, 2),
                    end_time=round(min(cur_st + self.max_dur, sub_end), 2),
                    text=self._wrap_lines(text_block),
                )
            )
        return subtitles

    def _clean_repetitive_stutter(self, text: str) -> str:
        """Deduplicates adjacent repetitive word/syllable stutter hallucinations (e.g. '안녕하세요. 녕하세요.', '반갑수다. 갑수다.', '쓰냐 쓰냐')."""
        cleaned = self._clean_repetitive_text(text)
        words = cleaned.split()
        if len(words) >= 2:
            new_words = []
            i = 0
            while i < len(words):
                if i + 1 < len(words):
                    w1_raw = words[i]
                    w2_raw = words[i + 1]
                    w1_clean = re.sub(r"[^\w]", "", w1_raw)
                    w2_clean = re.sub(r"[^\w]", "", w2_raw)

                    # Check prefix/suffix overlap (e.g. "안녕하세요" vs "녕하세요", "반갑수다" vs "갑수다")
                    if (
                        len(w1_clean) >= 3
                        and len(w2_clean) >= 2
                        and w1_clean.endswith(w2_clean)
                    ):
                        new_words.append(w1_raw)
                        i += 2
                        continue
                    # Check exact word repeat with punctuation (e.g. "쓰냐" vs "쓰냐")
                    elif w1_clean == w2_clean and len(w1_clean) >= 2:
                        new_words.append(w1_raw)
                        i += 2
                        continue
                new_words.append(words[i])
                i += 1
            cleaned = " ".join(new_words)
        return cleaned.strip()

    def _clean_repetitive_text(self, text: str) -> str:
        """Deduplicates repetitive hallucination loops (e.g. repeated words or infinite ㅋㅋㅋ)."""
        cleaned = re.sub(r"[ㅋ]{3,}", "ㅋㅋㅋ", text)
        cleaned = re.sub(r"[ㅎ]{3,}", "ㅎㅎㅎ", cleaned)
        cleaned = re.sub(r"[!]{3,}", "!!", cleaned)
        cleaned = re.sub(r"[?]{3,}", "??", cleaned)
        cleaned = re.sub(r"(\b\S+\b)(?:\s+\1){2,}", r"\1 \1", cleaned)
        return cleaned.strip()

    def _wrap_lines(self, text: str) -> str:
        """Splits long sentence into 2 lines if exceeds max_chars_per_line."""
        text = self._clean_repetitive_text(text)
        if len(text) <= self.max_chars:
            return text

        words = text.split(" ")
        lines = []
        cur_line = []

        for w in words:
            if sum(len(x) + 1 for x in cur_line) + len(w) > self.max_chars and cur_line:
                lines.append(" ".join(cur_line))
                cur_line = [w]
            else:
                cur_line.append(w)

        if cur_line:
            lines.append(" ".join(cur_line))

        return "\n".join(lines[: self.max_lines])
