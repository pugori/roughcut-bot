"""Unit tests for OpenTimelineIO universal timeline exporter."""

import pytest
import tempfile
from pathlib import Path
from channel_dna.core.exporter import OpenTimelineIOExporter, MarkerExporter
from channel_dna.core.models import ScanMarker


def test_otio_exporter():
    markers = [
        ScanMarker(start_time=10.0, end_time=25.0, duration=15.0, peak_tension=2.5, label="Highlight 01", reason="Laughter"),
        ScanMarker(start_time=60.0, end_time=90.0, duration=30.0, peak_tension=3.8, label="Highlight 02", reason="Hype Climax"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        otio_file = tmp / "test_timeline.otio"

        exp = OpenTimelineIOExporter()
        out_p = exp.export(markers, "test_vod.mp4", str(otio_file), fps=60.0)

        assert out_p.exists()
        assert out_p.stat().st_size > 500

        # Read back with opentimelineio
        import opentimelineio as otio
        timeline = otio.adapters.read_from_file(str(out_p))
        assert timeline.name.startswith("ChannelDNA")
        assert len(timeline.tracks) >= 1
        video_track = timeline.tracks[0]
        assert len(video_track) == 2
        assert video_track[0].name.startswith("Cut 01")
        assert video_track[1].name.startswith("Cut 02")


def test_marker_exporter_otio_integration():
    markers = [
        ScanMarker(start_time=5.0, end_time=15.0, duration=10.0, peak_tension=2.0),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        base_p = tmp / "streamer_vod.xml"

        exp = MarkerExporter()
        res = exp.export_all_formats(markers, "mock.mp4", str(base_p))

        assert "otio" in res
        assert Path(res["otio"]).exists()
        assert Path(res["otio"]).suffix == ".otio"
