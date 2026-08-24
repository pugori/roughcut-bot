import sys
sys.path.insert(0, r"c:\dna")
from pathlib import Path
from channel_dna.core.models import ScanMarker
from channel_dna.core.exporter import MarkerExporter

# AI가 추출했던 최종 5개 마커
markers = [
    ScanMarker(start_time=0.0, end_time=81.5, duration=81.5, peak_tension=5.60, label="Highlight 1", reason="Tension Peak"),
    ScanMarker(start_time=131.62, end_time=245.62, duration=114.0, peak_tension=5.24, label="Highlight 2", reason="Tension Peak"),
    ScanMarker(start_time=258.81, end_time=286.31, duration=27.5, peak_tension=0.76, label="Highlight 3", reason="Tension Peak"),
    ScanMarker(start_time=306.06, end_time=382.0, duration=75.9, peak_tension=3.03, label="Highlight 4", reason="Tension Peak"),
    ScanMarker(start_time=411.5, end_time=483.0, duration=71.5, peak_tension=2.15, label="Highlight 5", reason="Tension Peak"),
]

vod_path = r"C:\Users\cha85\Downloads\Chzzk_Dokcake_CaveDiver_11min.mp4"
base_out = r"c:\dna\output\accuracy_comparison\final_markers"

exporter = MarkerExporter()
res = exporter.export_all_formats(markers, vod_path, base_out)
print(f"Exported to: {res}")
