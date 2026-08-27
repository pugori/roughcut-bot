"""Global configuration and dynamic execution path management for ChannelDNA."""

import sys
from dataclasses import dataclass
from pathlib import Path

# Detect if running as a frozen PyInstaller executable
if getattr(sys, "frozen", False):
    # Running as compiled .exe: locate directory where the .exe itself resides
    BASE_DIR = Path(sys.executable).resolve().parent
    INTERNAL_RES_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    # Running from python source code
    BASE_DIR = Path(__file__).resolve().parent.parent
    INTERNAL_RES_DIR = BASE_DIR

# DB is always created and managed right next to the .exe / root workspace
DEFAULT_DB_PATH = BASE_DIR / "channel_dna.db"
DEFAULT_CACHE_DIR = BASE_DIR / ".cache"
DEFAULT_MARKER_DIR = BASE_DIR / "markers"


@dataclass
class AppConfig:
    # Base directories
    base_dir: Path = BASE_DIR
    internal_res_dir: Path = INTERNAL_RES_DIR
    default_db_path: Path = DEFAULT_DB_PATH
    default_cache_dir: Path = DEFAULT_CACHE_DIR
    default_marker_dir: Path = DEFAULT_MARKER_DIR

    # Audio Engineering
    sample_rate: int = 16000
    bandpass_low: float = 1000.0  # 1kHz
    bandpass_high: float = 3500.0  # 3.5kHz
    window_size_sec: float = 1.0
    hop_size_sec: float = 0.25
    chunk_duration_sec: float = 60.0

    # Scene & Cut Rhythm
    scene_threshold: float = 27.0
    scene_frame_skip: int = 2

    # Highlight & Scanner Buffers (Pro Editing Rules)
    buffer_before_sec: float = 3.0  # -3.0s lead-in buildup
    buffer_after_sec: float = 2.0  # +2.0s post-reaction cooldown
    min_marker_duration: float = 2.0
    merge_gap_sec: float = 2.0
    default_percentile: float = 85.0

    # Multiband Audio Analysis (Phase 2 Accuracy Improvement)
    multiband_ranges: dict = None  # Set in __post_init__
    multiband_weights: dict = None  # Set in __post_init__

    # Adaptive Threshold (Phase 3 Accuracy Improvement)
    adaptive_window_sec: float = 60.0  # Local adaptive threshold window
    onset_strength_weight: float = 0.20  # Weight for onset strength in tension blend

    # Chunk Overlap (Phase 3 Accuracy Improvement)
    chunk_overlap_sec: float = 5.0  # Overlap between processing chunks

    # DB & Resource Paths
    db_path: Path = DEFAULT_DB_PATH
    cache_dir: Path = DEFAULT_CACHE_DIR

    def __post_init__(self):
        if self.multiband_ranges is None:
            self.multiband_ranges = {
                "bass": (40.0, 250.0),  # Impact, bass drops
                "low_mid": (250.0, 1000.0),  # Male fundamental frequency
                "vocal": (300.0, 3400.0),  # Primary vocal tension band
                "presence": (3400.0, 7500.0),  # Screams, high-pitch reactions
            }
        if self.multiband_weights is None:
            self.multiband_weights = {
                "vocal": 0.50,  # Primary vocal tension
                "presence": 0.25,  # High-pitch excitement
                "bass": 0.10,  # Impact/bass energy
                "onset": 0.15,  # Sudden energy changes
            }


config = AppConfig()

