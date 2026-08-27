"""CMX 3600 EDL Exporters for DaVinci Resolve and CapCut PC."""

from pathlib import Path

from channel_dna.core.models import ScanMarker


class DavinciEdlExporter:
    """Exports CMX 3600 EDL for DaVinci Resolve."""

    def export(
        self,
        markers: list[ScanMarker],
        vod_file_path: str,
        output_path: str,
        fps: float = 30.0,
        video_file_name: str | None = None,
    ) -> Path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        if video_file_name:
            clean_stem = Path(video_file_name).stem
        else:
            if "http" in vod_file_path or not Path(vod_file_path).suffix:
                clean_stem = out_file.stem.replace("_davinci_markers", "").replace(
                    "_markers", ""
                )
            else:
                clean_stem = Path(vod_file_path).stem

        def frames_to_tc(f: int) -> str:
            ff = f % int(fps)
            ts = f // int(fps)
            ss = ts % 60
            mm = (ts // 60) % 60
            hh = ts // 3600
            return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

        lines = ["TITLE: ChannelDNA_Markers", "FCM: NON-DROP FRAME", ""]
        record_in = 0

        for i, m in enumerate(markers, 1):
            src_in = int(round(m.start_time * fps))
            src_out = int(round(m.end_time * fps))
            dur = src_out - src_in
            record_out = record_in + dur

            color = (
                "ResolveColorCyan"
                if "chat" in (m.reason or "").lower()
                else "ResolveColorRed"
                if m.peak_tension > 4.0
                else "ResolveColorBlue"
            )

            # CMX Edit event (Rough Cut)
            lines.append(
                f"{i:03d}  AX       V     C        {frames_to_tc(src_in)} {frames_to_tc(src_out)} {frames_to_tc(record_in)} {frames_to_tc(record_out)}"
            )
            lines.append(f"* FROM CLIP NAME: {clean_stem}.mp4")
            lines.append(f"* |C:{color} |M:Peak {m.peak_tension:.1f} |D:{dur}")
            lines.append("")
            record_in = record_out

        out_file.write_text("\n".join(lines), encoding="utf-8")
        return out_file


class CapcutEdlExporter:
    """Exports CapCut PC compatible CMX 3600 EDL and timeline cut definitions."""

    def export(
        self,
        markers: list[ScanMarker],
        vod_file_path: str,
        output_path: str,
        fps: float = 30.0,
        video_file_name: str | None = None,
    ) -> Path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        clean_stem = (
            Path(video_file_name).stem if video_file_name else Path(vod_file_path).stem
        )
        if "http" in clean_stem:
            clean_stem = out_file.stem.replace("_capcut_markers", "")

        def frames_to_tc(f: int) -> str:
            ff = f % int(fps)
            ts = f // int(fps)
            ss = ts % 60
            mm = (ts // 60) % 60
            hh = ts // 3600
            return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

        lines = ["TITLE: CapCut_RoughCut_Timeline", "FCM: NON-DROP FRAME", ""]
        record_in = 0

        for i, m in enumerate(markers, 1):
            src_in = int(round(m.start_time * fps))
            src_out = int(round(m.end_time * fps))
            dur = src_out - src_in
            record_out = record_in + dur

            lines.append(
                f"{i:03d}  AX       V     C        {frames_to_tc(src_in)} {frames_to_tc(src_out)} {frames_to_tc(record_in)} {frames_to_tc(record_out)}"
            )
            lines.append(f"* FROM CLIP NAME: {clean_stem}.mp4")
            lines.append(
                f"* |C:ResolveColorCyan |M:{m.label} (Peak {m.peak_tension:.1f}) |D:{dur}"
            )
            lines.append("")
            record_in = record_out

        out_file.write_text("\n".join(lines), encoding="utf-8")
        return out_file

