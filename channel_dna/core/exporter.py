"""Advanced NLE Exporter Facade for Premiere Pro, DaVinci Resolve, CapCut, OTIO, and Vrew."""

from pathlib import Path

from channel_dna.core.exporters.edl_exporter import (
    CapcutEdlExporter,
    DavinciEdlExporter,
)
from channel_dna.core.exporters.otio_exporter import OpenTimelineIOExporter
from channel_dna.core.exporters.vrew_exporter import VrewTableExporter
from channel_dna.core.exporters.xml_exporter import (
    PremiereXmlExporter,
    get_marker_color,
)
from channel_dna.core.models import ScanMarker
from channel_dna.core.utils import format_time_hhmmss

__all__ = [
    "CapcutEdlExporter",
    "DavinciEdlExporter",
    "MarkerExporter",
    "OpenTimelineIOExporter",
    "PremiereXmlExporter",
    "VrewTableExporter",
    "get_marker_color",
]


class MarkerExporter:
    """Consolidated Exporter Facade supporting 6 Industry Formats (XML, EDL, CapCut, OTIO, Vrew, CSV, TXT)."""

    def __init__(self):
        self.xml_exp = PremiereXmlExporter()
        self.edl_exp = DavinciEdlExporter()
        self.capcut_exp = CapcutEdlExporter()
        self.vrew_exp = VrewTableExporter()
        self.otio_exp = OpenTimelineIOExporter()

    def export(
        self,
        markers: list[ScanMarker],
        vod_file_path: str,
        output_path: str,
        export_format: str = "xml",
        fps: float = 30.0,
        video_file_name: str | None = None,
    ) -> Path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fmt = export_format.lower()
        if fmt == "xml":
            return self.xml_exp.export(
                markers,
                vod_file_path,
                output_path,
                fps=fps,
                video_file_name=video_file_name,
            )
        elif fmt == "edl":
            return self.edl_exp.export(
                markers,
                vod_file_path,
                output_path,
                fps=fps,
                video_file_name=video_file_name,
            )
        elif fmt == "capcut":
            return self.capcut_exp.export(
                markers,
                vod_file_path,
                output_path,
                fps=fps,
                video_file_name=video_file_name,
            )
        elif fmt == "otio":
            return self.otio_exp.export(
                markers,
                vod_file_path,
                output_path,
                fps=fps,
                video_file_name=video_file_name,
            )
        elif fmt == "vrew":
            return self.vrew_exp.export(markers, output_path)
        elif fmt == "csv":
            lines = ["Index,StartTime,EndTime,Duration,PeakTension,Label,Reason"]
            for i, m in enumerate(markers, 1):
                reason_str = m.reason or ""
                lines.append(
                    f'{i},{m.start_time:.2f},{m.end_time:.2f},{m.duration:.2f},{m.peak_tension:.2f},"{m.label}","{reason_str}"'
                )
            out_p.write_text("\n".join(lines), encoding="utf-8")
            return out_p
        elif fmt == "txt":
            lines = ["=== YouTube Chapter Timestamps ==="]
            for m in markers:
                lines.append(
                    f"{format_time_hhmmss(m.start_time)} {m.label} (텐션: {m.peak_tension:.1f}z)"
                )
            out_p.write_text("\n".join(lines), encoding="utf-8")
            return out_p
        else:
            return self.xml_exp.export(markers, vod_file_path, output_path, fps)

    def export_all_formats(
        self,
        markers: list[ScanMarker],
        vod_file_path: str,
        base_output_path: str,
        fps: float = 30.0,
    ) -> dict[str, str]:
        p = Path(base_output_path)
        stem = (
            p.stem.replace("_markers", "")
            .replace("_davinci", "")
            .replace("_premiere", "")
        )
        parent = p.parent
        xml_path = parent / f"{stem}_premiere_markers.xml"
        edl_path = parent / f"{stem}_davinci_markers.edl"
        capcut_path = parent / f"{stem}_capcut_markers.edl"
        otio_path = parent / f"{stem}_universal_timeline.otio"
        vrew_path = parent / f"{stem}_vrew_cut_table.csv"

        self.export(markers, vod_file_path, str(xml_path), export_format="xml", fps=fps)
        self.export(markers, vod_file_path, str(edl_path), export_format="edl", fps=fps)
        self.export(
            markers, vod_file_path, str(capcut_path), export_format="capcut", fps=fps
        )
        self.export(
            markers, vod_file_path, str(otio_path), export_format="otio", fps=fps
        )
        self.export(markers, vod_file_path, str(vrew_path), export_format="vrew")

        return {
            "xml": str(xml_path),
            "edl": str(edl_path),
            "capcut": str(capcut_path),
            "otio": str(otio_path),
            "vrew": str(vrew_path),
        }
