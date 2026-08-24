import pytest
import os
import subprocess
from pathlib import Path
import tempfile
import numpy as np

from channel_dna.core.guide_generator import GuideGenerator
from channel_dna.core.exporter import MarkerExporter, CapcutEdlExporter, VrewTableExporter
from channel_dna.core.rough_cut_renderer import RoughCutRenderer
from channel_dna.core.models import ScanMarker
from channel_dna.core.pipeline import PipelineFacade


def test_guide_generator_rules():
    """Verify that guide text follows the clean corporate memo format without marketing buzzwords."""
    text = GuideGenerator.generate_guide_text(
        vod_title="테스트 방송",
        vod_date="2026-08-22",
        total_markers=15,
    )

    # 1. Must NOT contain tool brand name or service words
    assert "ChannelDNA" not in text
    assert "channel_dna" not in text
    assert "서비스" not in text

    # 2. Must contain required corporate memo sections
    assert "[방송 정보]" in text
    assert "[중요: 원본 영상 파일명 설정]" in text
    assert "[파일 구성]" in text
    assert "[사용 방법]" in text
    assert "Solo (XML)" in text
    assert "Collab (XML)" in text
    assert "자막 (SRT)" in text

    # 3. Test saving to directory
    with tempfile.TemporaryDirectory() as tmpdir:
        p = GuideGenerator.save_guide_to_package(Path(tmpdir), "테스트 VOD")
        assert p.exists()
        assert p.name == "가이드.txt"
        assert p.stat().st_size > 100


def test_capcut_and_vrew_exporters():
    """Verify CapCut EDL and Vrew CSV generation."""
    markers = [
        ScanMarker(start_time=10.0, end_time=25.0, duration=15.0, peak_tension=2.5, label="Hype 01", reason="Laughter"),
        ScanMarker(start_time=60.0, end_time=90.0, duration=30.0, peak_tension=3.2, label="Hype 02", reason="Reaction"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        capcut_edl = tmp / "test_capcut.edl"
        vrew_csv = tmp / "test_vrew.csv"

        cap_exp = CapcutEdlExporter()
        cap_exp.export(markers, "mock_vod.mp4", str(capcut_edl))
        assert capcut_edl.exists()
        edl_content = capcut_edl.read_text(encoding="utf-8")
        assert "TITLE: CapCut_RoughCut_Timeline" in edl_content
        assert "FROM CLIP NAME" in edl_content

        vrew_exp = VrewTableExporter()
        vrew_exp.export(markers, str(vrew_csv))
        assert vrew_csv.exists()
        csv_content = vrew_csv.read_text(encoding="utf-8-sig")
        assert "시작시간,종료시간" in csv_content
        assert "00:00:10" in csv_content


def test_rough_cut_renderer_synthetic():
    """Generate synthetic test video and verify rough cut slicing and concatenation."""
    ffmpeg = shutil_which = "ffmpeg"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src_video = tmp / "test_src.mp4"
        out_rough_cut = tmp / "output_rough_cut.mp4"

        # Generate a short 10-second synthetic test video using ffmpeg
        gen_cmd = [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=10:size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
            "-c:v", "libx264", "-c:a", "aac",
            str(src_video)
        ]
        res = subprocess.run(gen_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            pytest.skip("FFmpeg not available for synthetic video test")

        assert src_video.exists()

        # Markers: 1.0s~3.0s and 5.0s~7.0s (total 4 seconds rough cut)
        markers = [
            ScanMarker(start_time=1.0, end_time=3.0, duration=2.0, peak_tension=1.8),
            ScanMarker(start_time=5.0, end_time=7.0, duration=2.0, peak_tension=2.2),
        ]

        renderer = RoughCutRenderer()
        out_p = renderer.render_full_rough_cut(
            vod_path=str(src_video),
            markers=markers,
            output_mp4_path=str(out_rough_cut),
        )

        assert out_p.exists()
        assert out_p.stat().st_size > 1000


