"""Proper Ground Truth extraction via audio fingerprint matching.
Maps YouTube edit segments back to original VOD timestamps using cross-correlation.
"""
import sys
sys.path.insert(0, r"c:\dna")
import json
import numpy as np
from pathlib import Path
from scipy.signal import correlate, butter, sosfilt

from channel_dna.core.audio_engine import AudioEngine

# Paths
VOD_PATH = str(Path.home() / "Downloads" / "Chzzk_Dokcake_CaveDiver_11min.mp4")
YOUTUBE_EDIT_PATH = str(Path.home() / "Downloads" / "YouTube_Dokcake_Edit_Psychopath.mp4")
OUTPUT_DIR = Path(r"c:\dna\output\accuracy_comparison")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

engine = AudioEngine()
sr = engine.sr  # 16000

print("=" * 70)
print("  GROUND TRUTH EXTRACTION via Audio Cross-Correlation")
print("=" * 70)

# 1. Load both audio streams
print("\n  Loading VOD audio...")
vod_audio = engine.extract_audio_in_memory(VOD_PATH)
vod_duration = len(vod_audio) / sr
print(f"  VOD: {len(vod_audio)} samples ({vod_duration:.1f}s)")

print("  Loading YouTube edit audio...")
edit_audio = engine.extract_audio_in_memory(YOUTUBE_EDIT_PATH)
edit_duration = len(edit_audio) / sr
print(f"  Edit: {len(edit_audio)} samples ({edit_duration:.1f}s)")

# 2. Bandpass filter to isolate vocal frequencies (more robust matching)
sos = butter(4, [300.0, 3400.0], btype="bandpass", fs=sr, output="sos")
vod_vocal = sosfilt(sos, vod_audio).astype(np.float32)
edit_vocal = sosfilt(sos, edit_audio).astype(np.float32)

# 3. Downsample for faster cross-correlation (4x = 4kHz)
downsample = 4
vod_ds = vod_vocal[::downsample]
edit_ds = edit_vocal[::downsample]
sr_ds = sr // downsample

print(f"\n  Cross-correlation matching (downsampled to {sr_ds}Hz)...")

# 4. Sliding window cross-correlation
# Split edit into chunks and find each chunk's position in VOD
chunk_duration_sec = 5.0  # 5-second chunks
chunk_len = int(chunk_duration_sec * sr_ds)
hop_sec = 2.5  # 2.5-second hops
hop_len = int(hop_sec * sr_ds)

n_chunks = max(1, (len(edit_ds) - chunk_len) // hop_len + 1)

matches = []
print(f"  Processing {n_chunks} chunks ({chunk_duration_sec}s each, {hop_sec}s hop)...")

for i in range(n_chunks):
    start_idx = i * hop_len
    end_idx = start_idx + chunk_len
    if end_idx > len(edit_ds):
        break
    
    chunk = edit_ds[start_idx:end_idx]
    
    # Normalize chunk
    chunk_norm = chunk - np.mean(chunk)
    chunk_std = np.std(chunk_norm)
    if chunk_std < 1e-6:
        continue
    chunk_norm = chunk_norm / chunk_std
    
    # Cross-correlate with VOD
    # Use a search window around expected position (edit time * vod/edit ratio)
    edit_time = (start_idx / sr_ds)
    expected_vod_time = edit_time * (vod_duration / edit_duration)
    
    # Search window: ±120 seconds around expected position
    search_margin = 120.0
    search_start = max(0, int((expected_vod_time - search_margin) * sr_ds))
    search_end = min(len(vod_ds), int((expected_vod_time + search_margin) * sr_ds) + chunk_len)
    
    vod_window = vod_ds[search_start:search_end]
    
    if len(vod_window) < chunk_len:
        continue
    
    # Normalized cross-correlation
    vod_norm = vod_window - np.mean(vod_window)
    vod_std = np.std(vod_norm)
    if vod_std < 1e-6:
        continue
    
    corr = correlate(vod_norm, chunk_norm, mode='valid')
    
    # Normalize correlation
    n = len(chunk_norm)
    # Rolling std of vod for proper normalization
    vod_sq = vod_norm ** 2
    cumsum = np.cumsum(vod_sq)
    cumsum = np.insert(cumsum, 0, 0)
    rolling_energy = cumsum[n:] - cumsum[:len(cumsum)-n]
    rolling_std = np.sqrt(np.maximum(rolling_energy / n, 1e-10))
    
    corr_normalized = corr / (rolling_std * chunk_std * n)
    
    best_offset = np.argmax(corr_normalized)
    best_corr = float(corr_normalized[best_offset])
    
    vod_match_time = (search_start + best_offset) / sr_ds
    
    if best_corr > 0.3:  # Minimum correlation threshold
        matches.append({
            "edit_time": round(edit_time, 2),
            "vod_time": round(vod_match_time, 2),
            "correlation": round(best_corr, 4),
            "chunk_duration": chunk_duration_sec,
        })
    
    if (i + 1) % 20 == 0:
        print(f"    Processed {i+1}/{n_chunks} chunks... (last corr={best_corr:.3f})")

print(f"\n  Matched {len(matches)} chunks out of {n_chunks} total")

# 5. Convert matches to VOD highlight segments
# Group consecutive matched chunks into segments
if matches:
    matches.sort(key=lambda x: x["vod_time"])
    
    # Build segments from matched chunks
    gt_segments = []
    seg_start = matches[0]["vod_time"]
    seg_end = seg_start + chunk_duration_sec
    seg_corrs = [matches[0]["correlation"]]
    
    for m in matches[1:]:
        if m["vod_time"] <= seg_end + 8.0:  # Merge if within 8 seconds
            seg_end = max(seg_end, m["vod_time"] + chunk_duration_sec)
            seg_corrs.append(m["correlation"])
        else:
            avg_corr = np.mean(seg_corrs)
            gt_segments.append({
                "start": round(seg_start, 2),
                "end": round(seg_end, 2),
                "duration": round(seg_end - seg_start, 2),
                "avg_correlation": round(avg_corr, 4),
                "n_matches": len(seg_corrs),
            })
            seg_start = m["vod_time"]
            seg_end = seg_start + chunk_duration_sec
            seg_corrs = [m["correlation"]]
    
    # Don't forget last segment
    avg_corr = np.mean(seg_corrs)
    gt_segments.append({
        "start": round(seg_start, 2),
        "end": round(seg_end, 2),
        "duration": round(seg_end - seg_start, 2),
        "avg_correlation": round(avg_corr, 4),
        "n_matches": len(seg_corrs),
    })
    
    # Filter: keep only segments with decent correlation and minimum duration
    gt_segments = [s for s in gt_segments if s["avg_correlation"] > 0.35 and s["duration"] >= 3.0]
else:
    gt_segments = []

print(f"\n  Ground Truth Segments (audio-matched): {len(gt_segments)}")
for i, seg in enumerate(gt_segments, 1):
    m = int(seg["start"] // 60)
    s = int(seg["start"] % 60)
    print(f"    GT #{i}: {m:02d}:{s:02d} ~ {int(seg['end']//60):02d}:{int(seg['end']%60):02d} ({seg['duration']:.1f}s, corr={seg['avg_correlation']:.3f})")

# 6. Save and run comparison
gt_data = {
    "source": YOUTUBE_EDIT_PATH,
    "method": "audio_cross_correlation",
    "segments": gt_segments,
    "total_segments": len(gt_segments),
    "raw_matches": matches[:20],  # Save first 20 for debugging
    "total_raw_matches": len(matches),
}

gt_path = OUTPUT_DIR / "ground_truth_audio_matched.json"
with open(gt_path, "w", encoding="utf-8") as f:
    json.dump(gt_data, f, ensure_ascii=False, indent=2)

# 7. Load baseline and improved markers
baseline_path = OUTPUT_DIR / "baseline_markers.json"
with open(baseline_path, "r", encoding="utf-8") as f:
    baseline_data = json.load(f)

# Re-run improved scan to get latest results
from channel_dna.core.scanner import VODScanner
from channel_dna.core.models import ChannelProfile

profile = ChannelProfile(
    profile_id="Dokcake", channel_name="Dokcake",
    avg_shot_length=3.5, tension_interval=45.0, silence_tolerance=0.8,
    highlight_rms_threshold=0.95, hook_duration=15.0, sample_count=0,
)

scanner = VODScanner(engine)
improved_markers = scanner.scan(VOD_PATH, profile, use_cache=True)

baseline_segs = [(m["start_time"], m["end_time"]) for m in baseline_data["markers"]]
improved_segs = [(m.start_time, m.end_time) for m in improved_markers]
gt_segs = [(s["start"], s["end"]) for s in gt_segments]

# 8. Compute IoU metrics
def compute_iou(a, b):
    inter_start = max(a[0], b[0])
    inter_end = min(a[1], b[1])
    inter = max(0, inter_end - inter_start)
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union > 0 else 0

def evaluate_markers(preds, gts, threshold=0.3):
    if not gts or not preds:
        return {"tp": 0, "fp": len(preds), "fn": len(gts), "precision": 0, "recall": 0, "f1": 0, "avg_iou": 0}
    
    # Build IoU matrix
    iou_matrix = []
    for pi, p in enumerate(preds):
        for gi, g in enumerate(gts):
            iou = compute_iou(p, g)
            if iou > 0:
                iou_matrix.append((iou, pi, gi))
    
    iou_matrix.sort(reverse=True)
    
    matched_preds = set()
    matched_gts = set()
    match_ious = []
    
    for iou, pi, gi in iou_matrix:
        if pi not in matched_preds and gi not in matched_gts and iou >= threshold:
            matched_preds.add(pi)
            matched_gts.add(gi)
            match_ious.append(iou)
    
    tp = len(match_ious)
    fp = len(preds) - tp
    fn = len(gts) - tp
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    avg_iou = np.mean(match_ious) if match_ious else 0
    
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "avg_iou": round(float(avg_iou), 4)}

# Coverage calculation
def calc_coverage(preds, gts, total_dur):
    # What % of GT time is covered by predictions
    gt_covered = 0
    for gs, ge in gts:
        for ps, pe in preds:
            overlap_start = max(gs, ps)
            overlap_end = min(ge, pe)
            if overlap_end > overlap_start:
                gt_covered += overlap_end - overlap_start
    
    total_gt_time = sum(ge - gs for gs, ge in gts)
    total_pred_time = sum(pe - ps for ps, pe in preds)
    
    gt_coverage = gt_covered / total_gt_time if total_gt_time > 0 else 0
    pred_efficiency = gt_covered / total_pred_time if total_pred_time > 0 else 0
    
    return {
        "gt_coverage": round(gt_coverage, 4),
        "pred_efficiency": round(pred_efficiency, 4),
        "gt_time_covered_sec": round(gt_covered, 1),
        "total_gt_time_sec": round(total_gt_time, 1),
        "total_pred_time_sec": round(total_pred_time, 1),
    }

# Run evaluation
print("\n" + "=" * 70)
print("  FINAL ACCURACY COMPARISON (Audio Cross-Correlation GT)")
print("=" * 70)

results = {"baseline": {}, "improved": {}}

for threshold in [0.1, 0.2, 0.3, 0.5]:
    b = evaluate_markers(baseline_segs, gt_segs, threshold)
    i = evaluate_markers(improved_segs, gt_segs, threshold)
    results["baseline"][f"iou_{threshold}"] = b
    results["improved"][f"iou_{threshold}"] = i

baseline_cov = calc_coverage(baseline_segs, gt_segs, vod_duration)
improved_cov = calc_coverage(improved_segs, gt_segs, vod_duration)

# Print comparison table
print(f"\n  VOD: {Path(VOD_PATH).name} ({vod_duration:.0f}s)")
print(f"  YouTube Edit → {len(gt_segs)} Ground Truth segments")
print(f"  Baseline: {len(baseline_segs)} markers | Improved: {len(improved_segs)} markers")

print(f"\n  {'Metric':<35} {'Baseline':>10} {'Improved':>10} {'Delta':>10}")
print(f"  {'-'*65}")

for threshold in [0.1, 0.2, 0.3, 0.5]:
    b = results["baseline"][f"iou_{threshold}"]
    i = results["improved"][f"iou_{threshold}"]
    delta_f1 = i["f1"] - b["f1"]
    delta_r = i["recall"] - b["recall"]
    delta_p = i["precision"] - b["precision"]
    
    print(f"  F1 @ IoU={threshold:<24} {b['f1']:>10.3f} {i['f1']:>10.3f} {delta_f1:>+10.3f}")
    print(f"  Precision @ IoU={threshold:<20} {b['precision']:>10.3f} {i['precision']:>10.3f} {delta_p:>+10.3f}")
    print(f"  Recall @ IoU={threshold:<23} {b['recall']:>10.3f} {i['recall']:>10.3f} {delta_r:>+10.3f}")
    print(f"  TP/FP/FN @ IoU={threshold:<21} {b['tp']}/{b['fp']}/{b['fn']}{'':>5} {i['tp']}/{i['fp']}/{i['fn']}")
    print()

print(f"\n  {'Coverage Metric':<35} {'Baseline':>10} {'Improved':>10}")
print(f"  {'-'*55}")
print(f"  {'GT Coverage (% of GT covered)':<35} {baseline_cov['gt_coverage']:>10.1%} {improved_cov['gt_coverage']:>10.1%}")
print(f"  {'Prediction Efficiency':<35} {baseline_cov['pred_efficiency']:>10.1%} {improved_cov['pred_efficiency']:>10.1%}")
print(f"  {'GT Time Covered (sec)':<35} {baseline_cov['gt_time_covered_sec']:>10.1f} {improved_cov['gt_time_covered_sec']:>10.1f}")
print(f"  {'Total GT Time (sec)':<35} {baseline_cov['total_gt_time_sec']:>10.1f} {improved_cov['total_gt_time_sec']:>10.1f}")
print(f"  {'Total Prediction Time (sec)':<35} {baseline_cov['total_pred_time_sec']:>10.1f} {improved_cov['total_pred_time_sec']:>10.1f}")

# Print baseline markers
print(f"\n  --- Baseline Markers ---")
for i, m in enumerate(baseline_data["markers"], 1):
    st = m["start_time"]
    et = m["end_time"]
    print(f"    #{i}: {int(st//60):02d}:{int(st%60):02d} ~ {int(et//60):02d}:{int(et%60):02d} ({m['duration']:.1f}s) peak={m['peak_tension']:.2f}")

# Print improved markers
print(f"\n  --- Improved Markers ---")
for i, m in enumerate(improved_markers, 1):
    print(f"    #{i}: {m.start_timecode} ~ {m.end_timecode} ({m.duration:.1f}s) peak={m.peak_tension:.2f}")

# Print GT segments
print(f"\n  --- Ground Truth Segments ---")
for i, seg in enumerate(gt_segments, 1):
    m = int(seg["start"] // 60)
    s = int(seg["start"] % 60)
    print(f"    GT #{i}: {m:02d}:{s:02d} ~ {int(seg['end']//60):02d}:{int(seg['end']%60):02d} ({seg['duration']:.1f}s, corr={seg['avg_correlation']:.3f})")

# Save final report
final_report = {
    "summary": {
        "vod": Path(VOD_PATH).name,
        "vod_duration": round(vod_duration, 1),
        "edit": Path(YOUTUBE_EDIT_PATH).name,
        "gt_method": "audio_cross_correlation",
        "gt_segments": len(gt_segs),
        "baseline_markers": len(baseline_segs),
        "improved_markers": len(improved_segs),
    },
    "evaluation": results,
    "coverage": {"baseline": baseline_cov, "improved": improved_cov},
    "baseline_markers": baseline_data["markers"],
    "improved_markers": [{"start": m.start_time, "end": m.end_time, "duration": m.duration, "peak": m.peak_tension} for m in improved_markers],
    "ground_truth": gt_segments,
}

final_path = OUTPUT_DIR / "final_comparison_report.json"
with open(final_path, "w", encoding="utf-8") as f:
    json.dump(final_report, f, ensure_ascii=False, indent=2)

print(f"\n  Full report saved: {final_path}")
print("=" * 70)
