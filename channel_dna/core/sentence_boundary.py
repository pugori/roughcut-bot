"""Sentence Boundary Refiner: Snaps highlight markers and subtitles to complete Korean sentence boundaries.
Prevents awkward mid-sentence cutoffs (e.g., '자고 일어나서 좀 센치해져서 그래서...') by expanding marker end_time to terminal predicates.
"""

import re
from typing import Any

from channel_dna.core.models import ScanMarker

# Korean terminal predicate endings and punctuation
TERMINAL_PUNCTUATION = (".", "?", "!", "~", "…")
TERMINAL_ENDINGS = (
    "다",
    "요",
    "죠",
    "네",
    "지",
    "어",
    "아",
    "음",
    "임",
    "까",
    "래",
    "군",
    "걸",
    "나",
    "자",
    "대",
    "잖아",
    "거든",
    "겠어",
    "게요",
    "니다",
    "시오",
    "세요",
    "래요",
    "네요",
    "군요",
    "던가",
    "테야",
)

# Connective / non-terminal endings that should be expanded further
CONNECTIVE_ENDINGS = (
    "고",
    "서",
    "며",
    "면",
    "서도",
    "는데",
    "은데",
    "은데도",
    "지만",
    "니까",
    "더니",
    "다가",
    "자마자",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "로",
    "과",
    "와",
    "랑",
    "도",
    "만",
    "서사",
)


class SentenceBoundaryRefiner:
    """Refines highlight marker boundaries based on complete Korean sentence termination."""

    def __init__(self, max_extension_sec: float = 3.5, max_pre_snap_sec: float = 1.5):
        self.max_extension = max_extension_sec
        self.max_pre_snap = max_pre_snap_sec

    def is_sentence_terminal(self, word_text: str) -> bool:
        """Checks if a word represents a natural sentence termination in Korean."""
        cleaned = re.sub(r"[^가-힣a-zA-Z0-9\.\?\!\~\…]+", "", word_text).strip()
        if not cleaned:
            return False

        # 1. Punctuation
        if any(cleaned.endswith(p) for p in TERMINAL_PUNCTUATION):
            return True

        # 2. Check if ends with connective ending (not terminal)
        for c in CONNECTIVE_ENDINGS:
            if cleaned.endswith(c) and not any(
                cleaned.endswith(t) for t in ["다", "요", "죠", "네"]
            ):
                return False

        # 3. Check if ends with terminal ending
        if any(cleaned.endswith(t) for t in TERMINAL_ENDINGS):
            return True

        return False

    def refine_marker_and_words(
        self, marker: ScanMarker, word_tokens: list[dict[str, Any]], slice_offset: float
    ) -> tuple[ScanMarker, list[dict[str, Any]]]:
        """Snaps marker start_time and end_time to complete Korean sentence boundaries.
        Returns: (refined_marker, filtered_complete_words with absolute VOD timestamps)
        """
        if not word_tokens:
            return marker, []

        abs_words = []
        for w in word_tokens:
            w_copy = dict(w)
            w_copy["abs_start"] = float(w.get("start", 0.0)) + slice_offset
            w_copy["abs_end"] = float(w.get("end", 0.0)) + slice_offset
            w_copy["start"] = w_copy["abs_start"]
            w_copy["end"] = w_copy["abs_end"]
            abs_words.append(w_copy)

        # 1. Snap Start Time: Find the true beginning of the sentence overlapping marker start
        new_start = marker.start_time
        for i, w in enumerate(abs_words):
            if w["abs_start"] >= (marker.start_time - self.max_pre_snap) and w[
                "abs_start"
            ] <= (marker.start_time + 1.0):
                if (
                    i == 0
                    or (w["abs_start"] - abs_words[i - 1]["abs_end"] >= 0.5)
                    or self.is_sentence_terminal(abs_words[i - 1]["word"])
                ):
                    new_start = min(marker.start_time, w["abs_start"])
                    break

        # 2. Snap End Time: Look ahead up to max_extension_sec to find complete terminal ending
        new_end = marker.end_time
        target_words = [w for w in abs_words if w["abs_end"] >= new_start]
        if not target_words:
            target_words = abs_words

        last_valid_terminal_idx = -1
        for i, w in enumerate(target_words):
            w_end = w["abs_end"]
            if w_end <= (marker.end_time + self.max_extension):
                if self.is_sentence_terminal(w["word"]):
                    last_valid_terminal_idx = i
            elif w_end > (marker.end_time + self.max_extension):
                break

        if last_valid_terminal_idx != -1:
            new_end = max(
                marker.end_time, target_words[last_valid_terminal_idx]["abs_end"]
            )
            final_words = target_words[: last_valid_terminal_idx + 1]
        else:
            # Fallback to words within marker range or target_words
            in_range_words = [
                w for w in target_words if w["abs_end"] <= (marker.end_time + 1.5)
            ]
            final_words = in_range_words if in_range_words else target_words
            if final_words:
                new_end = max(marker.end_time, final_words[-1]["abs_end"])

        # Populate start and end with absolute times for formatter
        for w in final_words:
            w["start"] = w["abs_start"]
            w["end"] = w["abs_end"]

        # Update marker
        refined_marker = ScanMarker(
            start_time=round(new_start, 2),
            end_time=round(new_end, 2),
            duration=round(new_end - new_start, 2),
            peak_tension=marker.peak_tension,
            label=marker.label,
            reason=marker.reason,
        )

        return refined_marker, final_words

