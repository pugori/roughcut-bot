"""Capture baseline (before improvement) scan results for A/B comparison."""
import sys
sys.path.insert(0, r"c:\dna")
import json
import time
import numpy as np
from pathlib import Path

from channel_dna.core.audio_engine import AudioEngine
from channel_dna.core.scanner import VODScanner
from channel_dna.core.models import ChannelProfile

VOD_PATH = str(Path.home() / "Downloads" / "Chzzk_Dokcake_CaveDiver_11min.mp4")
OUTPUT_DIR = Path(r"c:\dna\output\accuracy_comparison")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_MARKERS_PATH = OUTPUT_DIR / "baseline_markers.json"
BASELINE_TENSION_PATH = OUTPUT_DIR / "baseline_tension.json"

def progress(stage, pct, msg):
    print(f"  [{stage}] {pct*100:.0f}% - {msg}", flush=True)

print("=" * 60)
print("  BASELINE CAPTURE (Before Improvements)")
print("=" * 60)

# Create a default profile matching the channel
profile = ChannelProfile(
    profile_id="Dokcake",
    channel_name="Dokcake",
    avg_shot_length=3.5,
    tension_interval=45.0,
    silence_tolerance=0.8,
    highlight_rms_threshold=0.95,
    hook_duration=15.0,
    sample_count=0,
)

engine = AudioEngine()
scanner = VODScanner(engine)

# Clear any existing cache to ensure fresh computation
cache_dir = Path(r"c:\dna\.cache")
vod_stem = Path(VOD_PATH).stem
for f in cache_dir.glob(f"{vod_stem}*"):
    try:
        f.unlink()
        print(f"  Cleared cache: {f.name}")
    except Exception:
        pass

print(f"\n  VOD: {VOD_PATH}")
print(f"  Profile: {profile.channel_name} (ASL={profile.avg_shot_length}s, threshold={profile.highlight_rms_threshold})")
print()

start_time = time.time()

# Extract audio and compute tension (save raw tension for analysis)
print("  [1/3] Extracting audio...")
audio_samples = engine.extract_audio_in_memory(VOD_PATH)
print(f"        Audio loaded: {len(audio_samples)} samples ({len(audio_samples)/16000:.1f}s)")

print("  [2/3] Computing tension curve...")
times, tension = engine.compute_sliding_tension(audio_samples)
engine.save_cache(vod_stem, times, tension)
print(f"        Tension computed: {len(times)} frames")

# Save raw tension data
tension_data = {
    "times": times.tolist(),
    "tension": tension.tolist(),
    "stats": {
        "mean": float(np.mean(tension)),
        "std": float(np.std(tension)),
        "max": float(np.max(tension)),
        "min": float(np.min(tension)),
        "p75": float(np.percentile(tension, 75)),
        "p90": float(np.percentile(tension, 90)),
        "p95": float(np.percentile(tension, 95)),
    }
}
with open(BASELINE_TENSION_PATH, "w", encoding="utf-8") as f:
    json.dump(tension_data, f, ensure_ascii=False, indent=2)
print(f"        Tension stats: mean={tension_data['stats']['mean']:.3f}, max={tension_data['stats']['max']:.3f}")

print("  [3/3] Running full scan...")
markers = scanner.scan(VOD_PATH, profile, use_cache=True, progress_cb=progress)

elapsed = time.time() - start_time

# Save marker results
results = {
    "meta": {
        "version": "baseline",
        "vod_path": VOD_PATH,
        "elapsed_sec": round(elapsed, 2),
        "total_markers": len(markers),
        "profile": {
            "channel": profile.channel_name,
            "asl": profile.avg_shot_length,
            "threshold": profile.highlight_rms_threshold,
        }
    },
    "markers": []
}

for m in markers:
    results["markers"].append({
        "start_time": m.start_time,
        "end_time": m.end_time,
        "duration": m.duration,
        "peak_tension": m.peak_tension,
        "label": m.label,
        "reason": m.reason,
        "confidence": getattr(m, "confidence", 1.0),
    })

with open(BASELINE_MARKERS_PATH, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n{'=' * 60}")
print(f"  BASELINE COMPLETE")
print(f"  Markers: {len(markers)}")
print(f"  Elapsed: {elapsed:.1f}s")
for i, m in enumerate(markers, 1):
    print(f"    #{i}: {m.start_timecode} ~ {m.end_timecode} ({m.duration:.1f}s) peak={m.peak_tension:.2f}")
print(f"  Saved to: {BASELINE_MARKERS_PATH}")
print(f"{'=' * 60}")
