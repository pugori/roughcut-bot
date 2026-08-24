"""Data models for ChannelDNA."""

from channel_dna.core.logger import get_logger

_logger = get_logger(__name__)

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from channel_dna.core.subtitle_formatter import SubtitleItem


@dataclass
class VideoMetadata:
    video_id: str
    title: str
    duration: float
    avg_shot_length: float
    channel_name: str | None = None
    file_path: str | None = None
    video_type: str = "auto"  # 'auto', 'solo', 'collab'
    speech_density: float = 0.75  # Ratio of speech activity (0.0 ~ 1.0)
    laughter_score: float = 1.0  # Laughter/giggle frequency score
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "VideoMetadata":
        r = dict(row)
        return cls(
            video_id=r["video_id"],
            title=r["title"],
            duration=r["duration"],
            avg_shot_length=r["avg_shot_length"],
            channel_name=r.get("channel_name"),
            file_path=r.get("file_path"),
            video_type=r.get("video_type", "auto") or "auto",
            speech_density=r.get("speech_density", 0.75) or 0.75,
            laughter_score=r.get("laughter_score", 1.0) or 1.0,
            created_at=r.get("created_at", ""),
        )


@dataclass
class SegmentData:
    segment_id: int | None = None
    video_id: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    rms_peak: float = 0.0
    transcript: str = ""


@dataclass
class ChannelProfile:
    profile_id: str
    channel_name: str
    sample_count: int = 1
    avg_shot_length: float = 3.5  # Average shot duration (seconds)
    tension_interval: float = 45.0  # Dominant tension peak interval (seconds)
    silence_tolerance: float = 0.8  # Max allowed silence before cut (seconds)
    highlight_rms_threshold: float = 0.95  # Tension z-score threshold for highlight
    hook_duration: float = 15.0  # Recommended intro hook length (seconds)
    custom_vocab: str = ""  # Channel-specific hotwords, memes, and gaming keywords
    motif_template: list[float] | None = None  # Normalized 32-point build-up/climax curve
    youtube_url: str = ""  # Streamer's YouTube Channel URL
    chzzk_url: str = ""  # Streamer's Chzzk Channel URL
    profile_type: str = "all"  # 'all', 'solo', 'collab'
    host_voice_print: str | None = None  # JSON string of 20 MFCC vector
    narrative_quota: dict[str, float] | None = None  # {"intro": 0.40, "body": 0.40, "outro": 0.20}
    speech_density_weight: float = 0.65  # Weight for conversational speech density
    laughter_sensitivity: float = 1.20  # Sensitivity for laughter/pitch bursts
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ChannelProfile":
        r = dict(row)
        motif = None
        if r.get("motif_template"):
            try:
                motif = json.loads(r["motif_template"])
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)
        quota = None
        if r.get("narrative_quota"):
            try:
                quota = json.loads(r["narrative_quota"])
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)
        return cls(
            profile_id=r["profile_id"],
            channel_name=r["channel_name"],
            sample_count=r.get("sample_count", 1),
            avg_shot_length=r.get("avg_shot_length", 3.5),
            tension_interval=r.get("tension_interval", 45.0),
            silence_tolerance=r.get("silence_tolerance", 0.8),
            highlight_rms_threshold=r.get("highlight_rms_threshold", 0.95),
            hook_duration=r.get("hook_duration", 15.0),
            custom_vocab=r.get("custom_vocab", ""),
            motif_template=motif,
            youtube_url=r.get("youtube_url", ""),
            chzzk_url=r.get("chzzk_url", ""),
            profile_type=r.get("profile_type", "all") or "all",
            host_voice_print=r.get("host_voice_print"),
            narrative_quota=quota or {"intro": 0.40, "body": 0.40, "outro": 0.20},
            speech_density_weight=r.get("speech_density_weight", 0.65) or 0.65,
            laughter_sensitivity=r.get("laughter_sensitivity", 1.20) or 1.20,
            updated_at=r.get("updated_at", ""),
        )

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "channel_name": self.channel_name,
            "sample_count": self.sample_count,
            "avg_shot_length": self.avg_shot_length,
            "tension_interval": self.tension_interval,
            "silence_tolerance": self.silence_tolerance,
            "highlight_rms_threshold": self.highlight_rms_threshold,
            "hook_duration": self.hook_duration,
            "custom_vocab": self.custom_vocab,
            "motif_template": json.dumps(self.motif_template) if self.motif_template else None,
            "youtube_url": self.youtube_url,
            "chzzk_url": self.chzzk_url,
            "profile_type": self.profile_type,
            "host_voice_print": self.host_voice_print,
            "narrative_quota": json.dumps(self.narrative_quota) if self.narrative_quota else None,
            "speech_density_weight": self.speech_density_weight,
            "laughter_sensitivity": self.laughter_sensitivity,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "ChannelProfile | None":
        if not d:
            return None
        if isinstance(d, ChannelProfile):
            return d
        motif = d.get("motif_template")
        if isinstance(motif, str):
            try:
                motif = json.loads(motif)
            except Exception:
                pass
        quota = d.get("narrative_quota")
        if isinstance(quota, str):
            try:
                quota = json.loads(quota)
            except Exception:
                pass
        return cls(
            profile_id=d.get("profile_id", "default"),
            channel_name=d.get("channel_name", "Default"),
            sample_count=d.get("sample_count", 1),
            avg_shot_length=d.get("avg_shot_length", 3.5),
            tension_interval=d.get("tension_interval", 45.0),
            silence_tolerance=d.get("silence_tolerance", 0.8),
            highlight_rms_threshold=d.get("highlight_rms_threshold", 0.95),
            hook_duration=d.get("hook_duration", 15.0),
            custom_vocab=d.get("custom_vocab", ""),
            motif_template=motif,
            youtube_url=d.get("youtube_url", ""),
            chzzk_url=d.get("chzzk_url", ""),
            profile_type=d.get("profile_type", "all") or "all",
            host_voice_print=d.get("host_voice_print"),
            narrative_quota=quota or {"intro": 0.40, "body": 0.40, "outro": 0.20},
            speech_density_weight=d.get("speech_density_weight", 0.65) or 0.65,
            laughter_sensitivity=d.get("laughter_sensitivity", 1.20) or 1.20,
            updated_at=d.get("updated_at", ""),
        )


@dataclass
class ScanMarker:
    start_time: float  # Seconds in VOD
    end_time: float  # Seconds in VOD
    duration: float  # Seconds
    peak_tension: float  # Maximum tension score in segment
    label: str = ""  # Marker title/name in timeline
    reason: str = ""  # Why this cut was made
    speech_density: float = 0.0
    laughter_score: float = 0.0


@dataclass
class VideoAnalysisResult:
    video_id: str
    title: str
    duration: float
    avg_shot_length: float
    cuts: list[float]
    tension_curve: list[float]
    tension_times: list[float]
    dominant_tension_interval: float
    speech_density: float = 0.75
    laughter_score: float = 1.0
    segments: list[SegmentData] = field(default_factory=list)


ProgressCallback = Callable[[str, float, str], None]


PSYCHOLOGY_SOLO_PROFILE = ChannelProfile(
    profile_id="PSYCHOLOGY_SOLO",
    channel_name="PSYCHOLOGY_SOLO",
    avg_shot_length=3.8,
    silence_tolerance=0.8,
    highlight_rms_threshold=0.95,
    profile_type="solo",
    speech_density_weight=0.65,
    laughter_sensitivity=1.20,
    narrative_quota={"intro": 0.40, "body": 0.40, "outro": 0.20},
)

PSYCHOLOGY_COLLAB_PROFILE = ChannelProfile(
    profile_id="PSYCHOLOGY_COLLAB",
    channel_name="PSYCHOLOGY_COLLAB",
    avg_shot_length=2.2,
    silence_tolerance=1.2,
    highlight_rms_threshold=1.10,
    profile_type="collab",
    speech_density_weight=0.50,
    laughter_sensitivity=1.35,
    narrative_quota={"intro": 0.30, "body": 0.50, "outro": 0.20},
)
