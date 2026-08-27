"""Report Generator module.
Generates pure fact-based Markdown (.md) and Text (.txt) QA & Context Reports.
"""

from pathlib import Path

from channel_dna_local.core.models import ScanMarker
from channel_dna_local.core.risk_engine import IssueMatchItem
from channel_dna_local.core.utils import format_time_hhmmss


class ReportGenerator:
    """Generates local standalone fact-based QA & Context reports (No server, 0 cost)."""

    def generate_markdown_report(
        self,
        vod_title: str,
        vod_date: str,
        vod_duration_sec: float,
        markers: list[ScanMarker],
        issue_matches: list[IssueMatchItem],
        output_path: str,
    ) -> Path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        dur_str = format_time_hhmmss(vod_duration_sec)

        lines = [
            "# 📋 [ChannelDNA] 방송 분석 및 맥락 이슈 리포트",
            f"- **방송 제목:** {vod_title}",
            f"- **방송 일자:** {vod_date}",
            f"- **영상 길이:** {dur_str} | 검출된 하이라이트: {len(markers)}개 | 이슈 키워드 검출: {len(issue_matches)}건",
            "",
            "---",
            "",
            "### 💡 [키워드 맥락 정보]",
            "",
        ]

        if not issue_matches:
            lines.append("✓ 검출된 특이 이슈 키워드가 없습니다.")
            lines.append("")
        else:
            for i, match in enumerate(issue_matches, 1):
                lines.append(
                    f'#### {i}. [{match.timecode}] 키워드: "{match.keyword}" (분류: {match.category})'
                )
                lines.append(f'- **발언 전후 내용:** "{match.spoken_sentence}"')
                lines.append(f"- **이슈 배경 / 유래:** {match.origin_context}")
                lines.append("")

        lines.extend(["---", "", "### 📌 [타임스탬프 & 챕터]", ""])

        if markers:
            lines.append("00:00:00 - 방송 시작")
            for i, m in enumerate(markers, 1):
                s_time = format_time_hhmmss(m.start_time)
                lines.append(
                    f"{s_time} - [Cut {i:02d}] 텐션 피크 {m.peak_tension:.2f} (길이: {int(m.duration)}초)"
                )
        else:
            lines.append("00:00:00 - 방송 시작")

        lines.append("")
        out_file.write_text("\n".join(lines), encoding="utf-8")
        return out_file

    def generate_text_report(
        self,
        vod_title: str,
        vod_date: str,
        vod_duration_sec: float,
        markers: list[ScanMarker],
        issue_matches: list[IssueMatchItem],
        output_path: str,
    ) -> Path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        dur_str = format_time_hhmmss(vod_duration_sec)

        lines = [
            "==================================================",
            " [ChannelDNA] 방송 분석 및 맥락 이슈 리포트",
            "==================================================",
            f"- 방송 제목: {vod_title}",
            f"- 방송 일자: {vod_date}",
            f"- 영상 길이: {dur_str} | 하이라이트: {len(markers)}개 | 이슈 키워드: {len(issue_matches)}건",
            "--------------------------------------------------",
            "",
            "[1. 키워드 맥락 정보]",
            "",
        ]

        if not issue_matches:
            lines.append("✓ 검출된 특이 이슈 키워드가 없습니다.\n")
        else:
            for i, match in enumerate(issue_matches, 1):
                lines.append(
                    f'[{i}] [{match.timecode}] 키워드: "{match.keyword}" ({match.category})'
                )
                lines.append(f'    - 발언 내용: "{match.spoken_sentence}"')
                lines.append(f"    - 이슈 배경/유래: {match.origin_context}")
                lines.append("")

        lines.extend(
            [
                "--------------------------------------------------",
                "[2. 타임스탬프 & 챕터]",
                "",
            ]
        )

        if markers:
            lines.append("00:00:00 - 방송 시작")
            for i, m in enumerate(markers, 1):
                s_time = format_time_hhmmss(m.start_time)
                lines.append(
                    f"{s_time} - [Cut {i:02d}] 텐션 피크 {m.peak_tension:.2f} (길이: {int(m.duration)}초)"
                )

        out_file.write_text("\n".join(lines), encoding="utf-8")
        return out_file

