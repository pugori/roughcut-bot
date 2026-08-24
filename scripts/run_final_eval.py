"""ChannelDNA Final Accuracy & Subtitle Evaluation.
Runs the fully upgraded pipeline (DNA Motif + VAD Subtitles) on the VOD.
"""
import sys
sys.path.insert(0, r"c:\dna")
import json
import time
from pathlib import Path
import numpy as np

from channel_dna.core.audio_engine import AudioEngine
from channel_dna.core.scanner import VODScanner
from channel_dna.core.db import DBManager
from channel_dna.core.subtitles import SubtitleEngine
from channel_dna.core.accuracy_evaluator import AccuracyEvaluator, markers_to_segments

VOD_PATH = str(Path.home() / "Downloads" / "Chzzk_Dokcake_CaveDiver_11min.mp4")
OUTPUT_DIR = Path(r"c:\dna\output\accuracy_comparison")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FINAL_MARKERS_PATH = OUTPUT_DIR / "final_markers.json"
FINAL_SUBS_PATH = OUTPUT_DIR / "final_subtitles.srt"
GT_PATH = OUTPUT_DIR / "ground_truth_audio_matched.json"

print("=" * 70)
print("  CHANNELDNA FINAL EVALUATION (Markers & Subtitles)")
print("=" * 70)

# 1. Load Profile with updated DNA
db = DBManager()
profile = db.get_profile("Dokcake")
print(f"\n  Loaded Profile: {profile.channel_name}")
print(f"  Motif DNA Length: {len(profile.motif_template)} points")

# 2. Run Scanner
engine = AudioEngine()
scanner = VODScanner(engine)
sub_engine = SubtitleEngine(model_size="tiny")  # Use tiny for speed in test, quality is handled by VAD

start_time = time.time()
print("\n  [1/2] Scanning VOD with Channel DNA Motif...")

def progress(stage, pct, msg):
    print(f"    [{stage}] {pct*100:.0f}% - {msg}", flush=True)

markers = scanner.scan(VOD_PATH, profile, use_cache=True, progress_cb=progress)

print(f"\n  Detected {len(markers)} markers:")
for i, m in enumerate(markers, 1):
    print(f"    #{i}: {m.start_timecode} ~ {m.end_timecode} ({m.duration:.1f}s) peak={m.peak_tension:.2f}")

# 3. Generate Subtitles
print("\n  [2/2] Generating VAD-chunked Subtitles for markers...")
try:
    audio_data = engine.extract_audio_in_memory(VOD_PATH)
    subs = sub_engine.generate_subtitles_for_markers(
        audio_data=audio_data,
        markers=markers,
        custom_vocab_prompt="지존, 짜쳐, 개손해, 억까, ㅋㅋㅋㅋ",
        progress_cb=progress
    )
    
    # Save Subtitles
    sub_engine.export_srt(subs, str(FINAL_SUBS_PATH))
    print(f"\n  Generated {len(subs)} subtitle lines.")
    print(f"  Saved SRT to: {FINAL_SUBS_PATH}")
    
    # 4. Export Marker Files (XML, EDL)
    from channel_dna.core.exporter import MarkerExporter
    exporter = MarkerExporter()
    exp_files = exporter.export_all_formats(markers, VOD_PATH, str(FINAL_MARKERS_PATH))
    print(f"  Saved NLE Files: {exp_files}")

    # 5. Generate Youtube Description using Local LLM
    from channel_dna.core.llm_engine import LocalLLMEngine
    llm = LocalLLMEngine()
    if llm.is_available():
        desc_path = OUTPUT_DIR / "youtube_description.txt"
        print("\n  [3/3] Generating YouTube Description via Local LLM...")
        llm.generate_youtube_description(markers, str(desc_path))
        print(f"  Saved YouTube Description to: {desc_path}")
        
except Exception as e:
    print(f"  Error: {e}")
    subs = []

elapsed = time.time() - start_time
print(f"\n  Total Processing Time: {elapsed:.1f}s")

# 4. Accuracy Evaluation
print("\n  Evaluating Marker Accuracy against Audio-Matched Ground Truth...")
evaluator = AccuracyEvaluator()
try:
    with open(GT_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)
        gt_segs = [(s["start"], s["end"]) for s in gt_data["segments"]]
    
    pred_segs = markers_to_segments(markers)
    eval_results = {}
    
    print(f"\n  {'Metric':<25} {'Value':>10}")
    print(f"  {'-'*36}")
    
    for threshold in [0.1, 0.2, 0.3, 0.5]:
        res = evaluator.evaluate(pred_segs, gt_segs, [threshold])[f"iou_{threshold}"]
        eval_results[f"iou_{threshold}"] = res
        print(f"  F1 @ IoU={threshold:<15} {res['f1']:>10.3f}")
        print(f"  Precision @ IoU={threshold:<8} {res['precision']:>10.3f}")
        print(f"  Recall @ IoU={threshold:<11} {res['recall']:>10.3f}")
        print(f"  TP/FP/FN @ IoU={threshold:<9} {res['true_positives']}/{res['false_positives']}/{res['false_negatives']:>6}")
        print()
        
    cov = evaluator.compute_coverage(pred_segs, gt_segs, len(audio_data)/16000)
    print(f"  GT Coverage: {cov.get('gt_coverage_ratio', cov.get('gt_coverage_percent', 0)):>18.1%}")
    print(f"  Prediction Efficiency: {cov.get('prediction_coverage_ratio', cov.get('pred_outside_percent', 0)):>8.1%}")
    
except Exception as e:
    print(f"  Evaluation skipped: {e}")

print("\n" + "=" * 70)
