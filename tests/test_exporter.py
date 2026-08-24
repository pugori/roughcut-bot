from pathlib import Path
from channel_dna.core.models import ScanMarker
from channel_dna.core.exporter import MarkerExporter


def test_exporters(tmp_path):
    markers = [
        ScanMarker(start_time=10.0, end_time=20.0, duration=10.0, peak_tension=2.45, label="Highlight 1"),
        ScanMarker(start_time=45.0, end_time=55.0, duration=10.0, peak_tension=1.80, label="Highlight 2"),
    ]
    vod_path = "C:/Videos/test_vod.mp4"
    exporter = MarkerExporter()

    # 1. XML Export (Premiere Pro / FCP7 Specification)
    xml_out = tmp_path / "test.xml"
    res_xml = exporter.export(markers, vod_path, str(xml_out), export_format="xml")
    assert Path(res_xml).exists()
    xml_content = Path(res_xml).read_text(encoding="utf-8")
    assert "<xmeml" in xml_content
    assert "<media>" in xml_content
    assert "<video>" in xml_content
    assert "<track>" in xml_content
    assert "<clipitem" in xml_content

    # 2. EDL Export (DaVinci Resolve CMX 3600 Specification)
    edl_out = tmp_path / "test.edl"
    res_edl = exporter.export(markers, vod_path, str(edl_out), export_format="edl")
    assert Path(res_edl).exists()
    edl_content = Path(res_edl).read_text(encoding="utf-8")
    assert "TITLE: ChannelDNA_Markers" in edl_content
    assert "* |C:ResolveColor" in edl_content
    assert "FCM: NON-DROP FRAME" in edl_content

    # 3. Standard formats export (XML & EDL)
    base_out = tmp_path / "test_all"
    res_map = exporter.export_all_formats(markers, vod_path, str(base_out))
    assert "xml" in res_map
    assert "edl" in res_map
    assert Path(res_map["xml"]).exists()
    assert Path(res_map["edl"]).exists()

    # 4. SRT Subtitle Export
    from channel_dna.core.subtitle_formatter import SubtitleItem
    from channel_dna.core.subtitles import SubtitleEngine
    sub_eng = SubtitleEngine()
    subs = [
        SubtitleItem(index=1, start_time=10.0, end_time=15.0, text="첫번째 자막"),
        SubtitleItem(index=2, start_time=45.0, end_time=50.0, text="두번째 자막"),
    ]
    srt_out = tmp_path / "test.srt"
    res_srt = sub_eng.export_srt(subs, str(srt_out))
    assert Path(res_srt).exists()
    srt_content = Path(res_srt).read_text(encoding="utf-8")
    assert "00:00:10,000 --> 00:00:15,000" in srt_content
    assert "첫번째 자막" in srt_content
