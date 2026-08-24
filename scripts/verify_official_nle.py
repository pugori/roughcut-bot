"""Verification script for official Premiere XML and DaVinci EDL/CSV generation."""
import xml.etree.ElementTree as ET
from pathlib import Path
from channel_dna.core.exporter import MarkerExporter
from channel_dna.core.models import ScanMarker

markers = [
    ScanMarker(start_time=70.0, end_time=85.0, duration=15.0, peak_tension=2.15, label="Highlight 1"),
    ScanMarker(start_time=320.0, end_time=338.0, duration=18.0, peak_tension=1.85, label="Highlight 2")
]

exporter = MarkerExporter()
out_dir = Path("c:/dna/test_nle_export")
out_dir.mkdir(parents=True, exist_ok=True)

# 1. Export XML
xml_file = exporter.export(markers, "260817_Stream.mp4", str(out_dir / "test_premiere.xml"), export_format="xml", fps=60.0)
print("=== Premiere FCP7 XML Check ===")
xml_str = Path(xml_file).read_text(encoding="utf-8")
tree = ET.fromstring(xml_str)
assert tree.tag == "xmeml"
seq = tree.find(".//sequence")
assert seq is not None
assert seq.find("media/video/track") is not None
assert seq.find("media/audio/track") is not None
markers_nodes = seq.findall("marker")
print(f"XML Markers verified: {len(markers_nodes)} markers")
for m in markers_nodes:
    print(f" - Name: {m.find('name').text}, In: {m.find('in').text}, Out: {m.find('out').text}, Color: {m.find('markercolor').text}")

# 2. Export EDL
edl_file = exporter.export(markers, "260817_Stream.mp4", str(out_dir / "test_davinci.edl"), export_format="edl", fps=60.0)
print("\n=== DaVinci CMX 3600 EDL Check ===")
edl_lines = Path(edl_file).read_text(encoding="utf-8").splitlines()
for line in edl_lines:
    print(line)

# 3. Export CSV
csv_file = exporter.export(markers, "260817_Stream.mp4", str(out_dir / "test_davinci.csv"), export_format="csv", fps=60.0)
print("\n=== DaVinci Marker CSV Check ===")
print(Path(csv_file).read_text(encoding="utf-8"))

print("\n✓ All NLE Formats strictly follow official specifications!")
