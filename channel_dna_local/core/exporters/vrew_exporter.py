"""Vrew Cut Table and Text Exporters."""

from pathlib import Path

from channel_dna_local.core.models import ScanMarker
from channel_dna_local.core.utils import format_time_hhmmss


class VrewTableExporter:
    """Exports Vrew-compatible timestamp cut tables and sentence-aligned script data."""

    def export(self, markers: list[ScanMarker], output_path: str) -> Path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "번호,시작시간,종료시간,구간길이(초),텐션점수,하이라이트유형,추천포인트"
        ]
        for i, m in enumerate(markers, 1):
            st_str = format_time_hhmmss(m.start_time)
            et_str = format_time_hhmmss(m.end_time)
            reason_str = m.reason or ""
            lines.append(
                f'{i},{st_str},{et_str},{m.duration:.1f},{m.peak_tension:.1f},{m.label},"{reason_str}"'
            )

        out_file.write_text("\n".join(lines), encoding="utf-8-sig")
        return out_file

