"""FCP7 XML Exporter for Premiere Pro and DaVinci Resolve with 60fps Selects Sequence."""

import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from channel_dna_local.core.models import ScanMarker
from channel_dna_local.core.subtitle_formatter import SubtitleItem


def get_marker_color(reason: str, peak: float) -> str:
    """Returns color code based on peak tension and reason."""
    reason = reason.lower() if reason else ""
    if "chat" in reason or "채팅" in reason:
        return "cyan"
    if "humor" in reason or "laugh" in reason or "ㅋㅋ" in reason:
        return "purple"
    if peak >= 4.0:
        return "red"
    return "green"


class PremiereXmlExporter:
    """Exports FCP7 XML compatible with Adobe Premiere Pro, DaVinci Resolve, and Final Cut Pro."""

    def _create_file_node(
        self,
        parent: ET.Element,
        file_id: str,
        vod_name: str,
        path_url_val: str,
        timebase: int,
        is_ntsc: str,
        total_frames: int,
        full_def: bool = True,
    ) -> ET.Element:
        file_node = ET.SubElement(parent, "file", id=file_id)
        if not full_def:
            return file_node

        ET.SubElement(file_node, "name").text = vod_name
        ET.SubElement(file_node, "pathurl").text = path_url_val
        file_rate = ET.SubElement(file_node, "rate")
        ET.SubElement(file_rate, "timebase").text = str(timebase)
        ET.SubElement(file_rate, "ntsc").text = is_ntsc
        ET.SubElement(file_node, "duration").text = str(total_frames)

        # Standard NDF Timecode Definition for Universal Multi-OS & Multi-NLE Support
        tc_node = ET.SubElement(file_node, "timecode")
        tc_rate = ET.SubElement(tc_node, "rate")
        ET.SubElement(tc_rate, "timebase").text = str(timebase)
        ET.SubElement(tc_rate, "ntsc").text = is_ntsc
        ET.SubElement(tc_node, "string").text = "00:00:00:00"
        ET.SubElement(tc_node, "frame").text = "0"
        ET.SubElement(tc_node, "displayformat").text = "NDF"

        file_media = ET.SubElement(file_node, "media")
        f_vid = ET.SubElement(file_media, "video")
        ET.SubElement(f_vid, "duration").text = str(total_frames)
        f_vid_sc = ET.SubElement(ET.SubElement(f_vid, "samplecharacteristics"), "rate")
        ET.SubElement(f_vid_sc, "timebase").text = str(timebase)
        ET.SubElement(f_vid_sc, "ntsc").text = is_ntsc

        f_aud = ET.SubElement(file_media, "audio")
        ET.SubElement(f_aud, "duration").text = str(total_frames)
        f_aud_sc = ET.SubElement(f_aud, "samplecharacteristics")
        ET.SubElement(f_aud_sc, "samplerate").text = "48000"
        ET.SubElement(f_aud_sc, "depth").text = "16"
        ET.SubElement(f_aud, "channelcount").text = "2"

        ach1 = ET.SubElement(f_aud, "audiochannel")
        ET.SubElement(ach1, "sourcechannel").text = "1"
        ach2 = ET.SubElement(f_aud, "audiochannel")
        ET.SubElement(ach2, "sourcechannel").text = "2"
        return file_node

    def _create_text_clipitem(
        self,
        parent_track: ET.Element,
        clip_id: str,
        text: str,
        start_frame: int,
        end_frame: int,
        timebase: int,
        is_ntsc: str,
        total_frames: int,
        font_size: int = 48,
    ) -> ET.Element:
        """Creates a standard FCP7 Text/Title Generator clipitem compatible with Premiere Pro & DaVinci Resolve."""
        dur_f = max(1, end_frame - start_frame)
        clipitem = ET.SubElement(parent_track, "clipitem", id=clip_id)
        clip_name = text.replace("\n", " ").strip()
        if len(clip_name) > 30:
            clip_name = clip_name[:27] + "..."
        ET.SubElement(clipitem, "name").text = clip_name or "Subtitle"
        ET.SubElement(clipitem, "duration").text = str(total_frames)
        rate = ET.SubElement(clipitem, "rate")
        ET.SubElement(rate, "timebase").text = str(timebase)
        ET.SubElement(rate, "ntsc").text = is_ntsc
        ET.SubElement(clipitem, "start").text = str(start_frame)
        ET.SubElement(clipitem, "end").text = str(end_frame)
        ET.SubElement(clipitem, "in").text = "0"
        ET.SubElement(clipitem, "out").text = str(dur_f)

        effect = ET.SubElement(clipitem, "effect")
        ET.SubElement(effect, "name").text = "Text"
        ET.SubElement(effect, "effectid").text = "Text"
        ET.SubElement(effect, "effectcategory").text = "Text"
        ET.SubElement(effect, "effecttype").text = "generator"
        ET.SubElement(effect, "mediatype").text = "video"

        p_str = ET.SubElement(effect, "parameter")
        ET.SubElement(p_str, "parameterid").text = "str"
        ET.SubElement(p_str, "name").text = "Text"
        ET.SubElement(p_str, "value").text = text

        p_font = ET.SubElement(effect, "parameter")
        ET.SubElement(p_font, "parameterid").text = "font"
        ET.SubElement(p_font, "name").text = "Font"
        ET.SubElement(p_font, "value").text = "Arial"

        p_size = ET.SubElement(effect, "parameter")
        ET.SubElement(p_size, "parameterid").text = "fontsize"
        ET.SubElement(p_size, "name").text = "Size"
        ET.SubElement(p_size, "value").text = str(font_size)

        return clipitem

    def export(
        self,
        markers: list[ScanMarker],
        vod_file_path: str,
        output_path: str,
        fps: float = 60.0,
        export_format: str = "xml",
        video_file_name: str | None = None,
    ) -> Path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        # 1. Determine video file stem and name
        if video_file_name:
            clean_stem = Path(video_file_name).stem
            vod_name = video_file_name
        else:
            if "http" in vod_file_path or not Path(vod_file_path).suffix:
                clean_stem = (
                    out_file.stem.replace("_premiere_markers", "")
                    .replace("_markers", "")
                    .replace("_30fps", "")
                )
            else:
                clean_stem = Path(vod_file_path).stem
            vod_name = f"{clean_stem}.mp4"

        # Check if user already placed a video file with matching stem in the XML folder
        candidate_exts = [
            ".mp4",
            ".mkv",
            ".mov",
            ".ts",
            ".webm",
            ".avi",
            ".flv",
            ".m4v",
        ]
        for ext in candidate_exts:
            cand = out_file.parent / f"{clean_stem}{ext}"
            if cand.exists():
                vod_name = cand.name
                break

        # 2. Build standard RFC-compliant file://localhost/C:/... absolute URI
        target_video_file = (out_file.parent / vod_name).resolve()
        posix_path = target_video_file.as_posix()
        path_url_val = f"file://localhost/{urllib.parse.quote(posix_path, safe=':/')}"

        is_ntsc = "FALSE"
        if (abs(fps - 30) < 5 and abs(fps - 29.97) < abs(fps - 30.0)) or (
            abs(fps - 60) < 5 and abs(fps - 59.94) < abs(fps - 60.0)
        ):
            is_ntsc = "TRUE"

        timebase = 60
        if fps < 45:
            timebase = 30
        if abs(fps - 24) < 1.5:
            timebase = 24
        if abs(fps - 25) < 1.5:
            timebase = 25
        if abs(fps - 50) < 1.5:
            timebase = 50

        total_frames = (
            int(round((markers[-1].end_time + 60.0) * fps)) if markers else 72000
        )

        root = ET.Element("xmeml", version="4")
        project = ET.SubElement(root, "project")
        ET.SubElement(project, "name").text = f"ChannelDNA Project - {clean_stem}"
        children = ET.SubElement(project, "children")

        # Register File Media in Project Bin
        self._create_file_node(
            children,
            "vod-file-1",
            vod_name,
            path_url_val,
            timebase,
            is_ntsc,
            total_frames,
            full_def=True,
        )

        # Sequence 1: Rough Cut (Selects Timeline - Default for editors)
        seq_rough = ET.SubElement(children, "sequence", id="seq-rough")
        ET.SubElement(seq_rough, "name").text = f"[Rough Cut] {clean_stem} (Selects)"
        seq_r_rate = ET.SubElement(seq_rough, "rate")
        ET.SubElement(seq_r_rate, "timebase").text = str(timebase)
        ET.SubElement(seq_r_rate, "ntsc").text = is_ntsc
        seq_r_media = ET.SubElement(seq_rough, "media")

        # Video Media Track Setup
        v_media_r = ET.SubElement(seq_r_media, "video")
        v_format_r = ET.SubElement(v_media_r, "format")
        v_sc_r = ET.SubElement(v_format_r, "samplecharacteristics")
        v_sc_r_rate = ET.SubElement(v_sc_r, "rate")
        ET.SubElement(v_sc_r_rate, "timebase").text = str(timebase)
        ET.SubElement(v_sc_r_rate, "ntsc").text = is_ntsc
        ET.SubElement(v_sc_r, "width").text = "1920"
        ET.SubElement(v_sc_r, "height").text = "1080"

        # V1: Video Cut Track
        v1_track_r = ET.SubElement(v_media_r, "track")

        # Audio Media Tracks
        a_media_r = ET.SubElement(seq_r_media, "audio")
        a1_track_r = ET.SubElement(a_media_r, "track")
        a2_track_r = ET.SubElement(a_media_r, "track")

        current_timeline_frame = 0

        for i, m in enumerate(markers, 1):
            in_f = int(round(m.start_time * fps))
            out_f = int(round(m.end_time * fps))
            dur_f = max(1, out_f - in_f)

            # Video Clipitem (V1)
            v_clip_r = ET.SubElement(v1_track_r, "clipitem", id=f"clip-r-v-{i}")
            ET.SubElement(
                v_clip_r, "name"
            ).text = f"Cut {i:02d} (Peak {m.peak_tension:.1f})"
            ET.SubElement(v_clip_r, "duration").text = str(total_frames)
            c_rate_v = ET.SubElement(v_clip_r, "rate")
            ET.SubElement(c_rate_v, "timebase").text = str(timebase)
            ET.SubElement(c_rate_v, "ntsc").text = is_ntsc
            ET.SubElement(v_clip_r, "start").text = str(current_timeline_frame)
            ET.SubElement(v_clip_r, "end").text = str(current_timeline_frame + dur_f)
            ET.SubElement(v_clip_r, "in").text = str(in_f)
            ET.SubElement(v_clip_r, "out").text = str(out_f)

            # First video clip item gets full file definition for DaVinci Resolve & Premiere compatibility
            self._create_file_node(
                v_clip_r,
                "vod-file-1",
                vod_name,
                path_url_val,
                timebase,
                is_ntsc,
                total_frames,
                full_def=(i == 1),
            )

            l_v = ET.SubElement(v_clip_r, "link")
            ET.SubElement(l_v, "linkclipref").text = f"clip-r-v-{i}"
            ET.SubElement(l_v, "mediatype").text = "video"
            ET.SubElement(l_v, "trackindex").text = "1"
            ET.SubElement(l_v, "clipindex").text = str(i)

            l_a1 = ET.SubElement(v_clip_r, "link")
            ET.SubElement(l_a1, "linkclipref").text = f"clip-r-a1-{i}"
            ET.SubElement(l_a1, "mediatype").text = "audio"
            ET.SubElement(l_a1, "trackindex").text = "1"
            ET.SubElement(l_a1, "clipindex").text = str(i)
            ET.SubElement(l_a1, "groupindex").text = "1"

            l_a2 = ET.SubElement(v_clip_r, "link")
            ET.SubElement(l_a2, "linkclipref").text = f"clip-r-a2-{i}"
            ET.SubElement(l_a2, "mediatype").text = "audio"
            ET.SubElement(l_a2, "trackindex").text = "2"
            ET.SubElement(l_a2, "clipindex").text = str(i)
            ET.SubElement(l_a2, "groupindex").text = "1"

            # Audio Clip Left (Track 1)
            a1_clip_r = ET.SubElement(a1_track_r, "clipitem", id=f"clip-r-a1-{i}")
            ET.SubElement(
                a1_clip_r, "name"
            ).text = f"Cut {i:02d} (Peak {m.peak_tension:.1f})"
            ET.SubElement(a1_clip_r, "duration").text = str(total_frames)
            c_rate_a1 = ET.SubElement(a1_clip_r, "rate")
            ET.SubElement(c_rate_a1, "timebase").text = str(timebase)
            ET.SubElement(c_rate_a1, "ntsc").text = is_ntsc
            ET.SubElement(a1_clip_r, "start").text = str(current_timeline_frame)
            ET.SubElement(a1_clip_r, "end").text = str(current_timeline_frame + dur_f)
            ET.SubElement(a1_clip_r, "in").text = str(in_f)
            ET.SubElement(a1_clip_r, "out").text = str(out_f)
            st_a1 = ET.SubElement(a1_clip_r, "sourcetrack")
            ET.SubElement(st_a1, "mediatype").text = "audio"
            ET.SubElement(st_a1, "trackindex").text = "1"
            ET.SubElement(a1_clip_r, "file", id="vod-file-1")

            la1_v = ET.SubElement(a1_clip_r, "link")
            ET.SubElement(la1_v, "linkclipref").text = f"clip-r-v-{i}"
            ET.SubElement(la1_v, "mediatype").text = "video"
            ET.SubElement(la1_v, "trackindex").text = "1"
            ET.SubElement(la1_v, "clipindex").text = str(i)

            la1_a1 = ET.SubElement(a1_clip_r, "link")
            ET.SubElement(la1_a1, "linkclipref").text = f"clip-r-a1-{i}"
            ET.SubElement(la1_a1, "mediatype").text = "audio"
            ET.SubElement(la1_a1, "trackindex").text = "1"
            ET.SubElement(la1_a1, "clipindex").text = str(i)
            ET.SubElement(la1_a1, "groupindex").text = "1"

            # Audio Clip Right (Track 2)
            a2_clip_r = ET.SubElement(a2_track_r, "clipitem", id=f"clip-r-a2-{i}")
            ET.SubElement(
                a2_clip_r, "name"
            ).text = f"Cut {i:02d} (Peak {m.peak_tension:.1f})"
            ET.SubElement(a2_clip_r, "duration").text = str(total_frames)
            c_rate_a2 = ET.SubElement(a2_clip_r, "rate")
            ET.SubElement(c_rate_a2, "timebase").text = str(timebase)
            ET.SubElement(c_rate_a2, "ntsc").text = is_ntsc
            ET.SubElement(a2_clip_r, "start").text = str(current_timeline_frame)
            ET.SubElement(a2_clip_r, "end").text = str(current_timeline_frame + dur_f)
            ET.SubElement(a2_clip_r, "in").text = str(in_f)
            ET.SubElement(a2_clip_r, "out").text = str(out_f)
            st_a2 = ET.SubElement(a2_clip_r, "sourcetrack")
            ET.SubElement(st_a2, "mediatype").text = "audio"
            ET.SubElement(st_a2, "trackindex").text = "2"
            ET.SubElement(a2_clip_r, "file", id="vod-file-1")

            la2_v = ET.SubElement(a2_clip_r, "link")
            ET.SubElement(la2_v, "linkclipref").text = f"clip-r-v-{i}"
            ET.SubElement(la2_v, "mediatype").text = "video"
            ET.SubElement(la2_v, "trackindex").text = "1"
            ET.SubElement(la2_v, "clipindex").text = str(i)

            la2_a2 = ET.SubElement(a2_clip_r, "link")
            ET.SubElement(la2_a2, "linkclipref").text = f"clip-r-a2-{i}"
            ET.SubElement(la2_a2, "mediatype").text = "audio"
            ET.SubElement(la2_a2, "trackindex").text = "2"
            ET.SubElement(la2_a2, "clipindex").text = str(i)
            ET.SubElement(la2_a2, "groupindex").text = "1"
            current_timeline_frame += dur_f

        ET.SubElement(seq_rough, "duration").text = str(current_timeline_frame)

        # Write XML with XML declaration
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ", level=0)
        tree.write(str(out_file), encoding="utf-8", xml_declaration=True)
        return out_file


