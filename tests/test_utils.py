"""Unit tests for channel_dna.core.utils."""

from channel_dna.core.utils import (
    sanitize_filename,
    build_vod_folder_and_filenames,
    get_channel_marker_dir,
    format_duration_kr,
)


def test_sanitize_filename():
    assert sanitize_filename("26.08.17 1부 다이브!?:*") == "26.08.17 1부 다이브"
    assert sanitize_filename("") == "VOD_Highlight"
    assert sanitize_filename(None) == "VOD_Highlight"
    assert len(sanitize_filename("A" * 100, max_length=20)) == 20


def test_build_vod_folder_and_filenames():
    folder, xml, edl, srt = build_vod_folder_and_filenames("2026-08-17", "1부 다이브오어다이")
    assert folder == "20260817_1부 다이브오어다이"
    assert xml == "20260817_1부 다이브오어다이.xml"
    assert edl == "20260817_1부 다이브오어다이.edl"
    assert srt == "20260817_1부 다이브오어다이.srt"


def test_format_duration_kr():
    assert format_duration_kr(3665) == "1시간 1분 5초"
    assert format_duration_kr(3600) == "1시간 0분"
    assert format_duration_kr(125) == "2분 5초"
    assert format_duration_kr(45) == "45초"
