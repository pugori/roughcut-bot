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


def test_xml_multi_speaker_subtitle_tracks(tmp_path):
    """Verifies that FCPXML exports V1 (video), V2 (streamer), V3 (guest), V4 (donation) subtitle tracks."""
    import xml.etree.ElementTree as ET
    from channel_dna.core.exporter import MarkerExporter
    from channel_dna.core.models import ScanMarker
    from channel_dna.core.subtitle_formatter import SubtitleItem

    markers = [
        ScanMarker(start_time=0.0, end_time=30.0, duration=30.0, peak_tension=3.0, label="Cut 01"),
    ]
    subs = [
        SubtitleItem(index=1, start_time=1.0, end_time=5.0, text="[화자 1] 안녕하세요 스트리머입니다."),
        SubtitleItem(index=2, start_time=6.0, end_time=10.0, text="[화자 2] 반갑습니다 게스트입니다."),
        SubtitleItem(index=3, start_time=11.0, end_time=15.0, text="[도네] 만원 후원 감사합니다!"),
    ]

    exporter = MarkerExporter()

    # 1. Collab Mode XML -> Should contain 4 Video Tracks (V1: Video, V2: Streamer, V3: Guest, V4: Donation)
    collab_xml = tmp_path / "collab_test.xml"
    exporter.export(
        markers,
        "test.mp4",
        str(collab_xml),
        export_format="xml",
        subtitles=subs,
        profile_type="collab",
    )
    assert collab_xml.exists()
    tree = ET.parse(str(collab_xml))
    root = tree.getroot()
    video_elem = root.find(".//sequence/media/video")
    assert video_elem is not None
    tracks = video_elem.findall("track")
    assert len(tracks) == 4  # V1, V2, V3, V4

    # Verify Generator Effect in Track 2 (V2 - Streamer)
    v2_clip = tracks[1].find(".//clipitem")
    assert v2_clip is not None
    v2_text_val = v2_clip.find(".//effect/parameter[parameterid='str']/value")
    assert v2_text_val is not None and "안녕하세요 스트리머입니다." in v2_text_val.text

    # Verify Generator Effect in Track 3 (V3 - Guest)
    v3_clip = tracks[2].find(".//clipitem")
    assert v3_clip is not None
    v3_text_val = v3_clip.find(".//effect/parameter[parameterid='str']/value")
    assert v3_text_val is not None and "반갑습니다 게스트입니다." in v3_text_val.text

    # Verify Generator Effect in Track 4 (V4 - Donation)
    v4_clip = tracks[3].find(".//clipitem")
    assert v4_clip is not None
    v4_text_val = v4_clip.find(".//effect/parameter[parameterid='str']/value")
    assert v4_text_val is not None and "만원 후원 감사합니다!" in v4_text_val.text

    # 2. Solo Mode XML -> Should contain 2 Video Tracks (V1: Video, V2: Streamer)
    solo_xml = tmp_path / "solo_test.xml"
    exporter.export(
        markers,
        "test.mp4",
        str(solo_xml),
        export_format="xml",
        subtitles=subs,
        profile_type="solo",
    )
    assert solo_xml.exists()
    solo_tree = ET.parse(str(solo_xml))
    solo_root = solo_tree.getroot()
    solo_video_elem = solo_root.find(".//sequence/media/video")
    assert solo_video_elem is not None
    solo_tracks = solo_video_elem.findall("track")
    assert len(solo_tracks) == 2  # V1, V2


def test_local_profile_json_export_import(tmp_path):
    """Verifies that ChannelProfile can be cleanly exported to and imported from local_profile.json."""
    from channel_dna.core.models import ChannelProfile
    from channel_dna.core.pipeline import PipelineFacade

    facade = PipelineFacade()
    prof = ChannelProfile(
        profile_id="test_streamer_Solo",
        channel_name="test_streamer",
        avg_shot_length=4.2,
        silence_tolerance=0.85,
        highlight_rms_threshold=0.92,
        profile_type="solo",
        custom_vocab="테스트, 방송",
    )

    json_file = tmp_path / "local_profile.json"
    facade.export_profile_json(prof, json_file)
    assert json_file.exists()

    imported = facade.import_profile_json(json_file, save_to_db=False)
    assert imported.profile_id == "test_streamer_Solo"
    assert imported.avg_shot_length == 4.2
    assert imported.silence_tolerance == 0.85
    assert imported.custom_vocab == "테스트, 방송"

