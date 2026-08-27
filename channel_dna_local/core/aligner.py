"""VOD Aligner module: aligns finished dialogue with raw VOD dialogue to infer speed ramping and cutting tolerance."""

from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz, process


@dataclass
class AlignmentMatch:
    finished_transcript: str
    raw_transcript: str
    finished_start: float
    finished_end: float
    raw_start: float
    raw_end: float
    similarity_score: float
    estimated_speed_ramp: float  # (finished_dur / raw_dur)
    silence_gap_before: float


class VODAligner:
    def __init__(self, match_threshold: float = 75.0):
        self.match_threshold = match_threshold

    def align_transcripts(
        self,
        finished_segments: list[dict[str, Any]],
        raw_segments: list[dict[str, Any]],
    ) -> list[AlignmentMatch]:
        """
        Align dialogue segments using fuzzy string matching and calculate speed ramps.
        finished_segments: list of {"start": float, "end": float, "text": str}
        raw_segments: list of {"start": float, "end": float, "text": str}
        """
        matches: list[AlignmentMatch] = []
        raw_texts = [s["text"] for s in raw_segments]

        prev_raw_end = 0.0

        for f_seg in finished_segments:
            f_text = f_seg["text"]
            if not f_text.strip():
                continue

            # Find best matching raw segment
            match = process.extractOne(
                f_text,
                raw_texts,
                scorer=fuzz.partial_ratio,
                score_cutoff=self.match_threshold,
            )

            if match:
                best_text, score, best_idx = match
                r_seg = raw_segments[best_idx]

                f_dur = max(0.1, f_seg["end"] - f_seg["start"])
                r_dur = max(0.1, r_seg["end"] - r_seg["start"])
                speed_ramp = round(f_dur / r_dur, 2)
                silence_gap = max(0.0, r_seg["start"] - prev_raw_end)

                matches.append(
                    AlignmentMatch(
                        finished_transcript=f_text,
                        raw_transcript=r_seg["text"],
                        finished_start=f_seg["start"],
                        finished_end=f_seg["end"],
                        raw_start=r_seg["start"],
                        raw_end=r_seg["end"],
                        similarity_score=score,
                        estimated_speed_ramp=speed_ramp,
                        silence_gap_before=round(silence_gap, 2),
                    )
                )

                prev_raw_end = r_seg["end"]

        return matches
