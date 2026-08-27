import math
import re
import urllib.parse
from xml.etree import ElementTree as ET
from pathlib import Path
from channel_dna.core.models import ScanMarker
from channel_dna.core.subtitle_formatter import SubtitleItem


class FcpxmlExporter:
    """Exports Final Cut Pro X XML (.fcpxml) specifically formatted for DaVinci Resolve & FCPX."""

    def _get_fraction(self, fps: float) -> tuple[int, int]:
        if abs(fps - 23.976) < 0.1:
            return 24000, 1001
        elif abs(fps - 29.97) < 0.1:
            return 30000, 1001
        elif abs(fps - 59.94) < 0.1:
            return 60000, 1001
        else:
            return int(round(fps)), 1

    def _frames_to_time_str(self, frames: int, num: int, den: int) -> str:
        if frames == 0:
            return "0s"
        value = frames * den
        gcd = math.gcd(value, num)
        v = value // gcd
        s = num // gcd
        if s == 1:
            return f"{v}s"
        return f"{v}/{s}s"

    def export(
        self,
        markers: list[ScanMarker],
        vod_file_path: str,
        output_path: str,
        fps: float = 60.0,
        video_file_name: str | None = None,
    ) -> Path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        if video_file_name:
            clean_stem = Path(video_file_name).stem
            vod_name = video_file_name
        else:
            clean_stem = Path(vod_file_path).stem
            vod_name = f"{clean_stem}.mp4"

        target_video_file = (out_file.parent / vod_name).resolve()
        posix_path = target_video_file.as_posix()
        path_url_val = f"file://localhost/{urllib.parse.quote(posix_path, safe=':/')}"

        num, den = self._get_fraction(fps)
        frame_duration = self._frames_to_time_str(1, num, den)

        last_m_end = max(m.end_time for m in markers) if markers else 0
        total_asset_frames = int(round((last_m_end + 3600) * fps))
        asset_dur = self._frames_to_time_str(total_asset_frames, num, den)

        root = ET.Element("fcpxml", version="1.9")
        resources = ET.SubElement(root, "resources")

        ET.SubElement(
            resources,
            "format",
            id="r1",
            name="FFVideoFormat1080p",
            frameDuration=frame_duration,
            width="1920",
            height="1080",
            colorSpace="1-1-1 (Rec. 709)",
        )
        ET.SubElement(
            resources,
            "asset",
            id="r2",
            name=vod_name,
            src=path_url_val,
            start="0s",
            duration=asset_dur,
            hasVideo="1",
            format="r1",
            hasAudio="1",
            audioSources="1",
            audioChannels="2",
            audioRate="48000",
        )

        ET.SubElement(
            resources,
            "effect",
            id="r3",
            name="Basic Title",
            uid=".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti",
        )

        library = ET.SubElement(root, "library")
        event = ET.SubElement(library, "event", name="ChannelDNA")
        project = ET.SubElement(event, "project", name=f"[Rough Cut] {clean_stem}")
        sequence = ET.SubElement(
            project,
            "sequence",
            format="r1",
            tcStart="0s",
            tcFormat="NDF",
            audioLayout="stereo",
            audioRate="48000",
        )
        spine = ET.SubElement(sequence, "spine")

        current_timeline_frame = 0

        for i, m in enumerate(markers, 1):
            in_f = int(round(m.start_time * fps))
            out_f = int(round(m.end_time * fps))
            dur_f = max(1, out_f - in_f)

            clip_offset = self._frames_to_time_str(current_timeline_frame, num, den)
            clip_dur = self._frames_to_time_str(dur_f, num, den)
            clip_start = self._frames_to_time_str(in_f, num, den)

            clip = ET.SubElement(
                spine,
                "asset-clip",
                name=f"Cut {i:02d}",
                ref="r2",
                offset=clip_offset,
                duration=clip_dur,
                start=clip_start,
                audioRole="dialogue",
            )

            current_timeline_frame += dur_f

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ", level=0)

        with open(out_file, "wb") as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(b"<!DOCTYPE fcpxml>\n")
            tree.write(f, encoding="utf-8")

        return out_file
