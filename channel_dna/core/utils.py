"""Common utility functions for ChannelDNA."""

import re
from pathlib import Path

from channel_dna.config import config


def sanitize_filename(
    name: str, max_length: int = 40, fallback: str = "VOD_Highlight"
) -> str:
    r"""Sanitizes a string to make it safe for Windows/Linux filenames and directory names.

    Removes invalid characters (\ / : * ? " < > |), trims whitespace, and limits length to avoid Windows MAX_PATH issues.
    """
    if not name:
        return fallback

    # Strip invalid characters for file systems (keep Korean, English, digits, spaces, and safe symbols)
    cleaned = re.sub(r"[^a-zA-Z0-9가-힣ㄱ-ㅎㅏ-ㅣ\s._\-\(\)\[\]]", "", name).strip()
    # Replace multiple consecutive spaces with a single space
    cleaned = re.sub(r"\s+", " ", cleaned)

    if not cleaned:
        return fallback

    return cleaned[:max_length].strip()


def build_vod_folder_and_filenames(
    vod_date: str, vod_title: str, max_title_len: int = 40
) -> tuple[str, str, str, str]:
    """Generates standard Google Drive folder name and package names (XML, EDL, SRT).

    Returns:
        (folder_name, xml_filename, edl_filename, srt_filename)
    """
    clean_date = vod_date.replace(".", "").replace("-", "").strip()
    clean_title = sanitize_filename(vod_title, max_length=max_title_len)

    folder_name = f"{clean_date}_{clean_title}" if clean_date else clean_title
    xml_name = f"{folder_name}.xml"
    edl_name = f"{folder_name}.edl"
    srt_name = f"{folder_name}.srt"

    return folder_name, xml_name, edl_name, srt_name


def create_streamer_notice_text(streamer_name: str = "") -> str:
    """Generates clean standard notice text for Google Drive streamer root folder."""
    return """================================================================================
  [📌 안내] 하이라이트 가편집 및 초벌 자막 참고용 데이터
================================================================================

본 데이터는 방송 활동과 유튜브 영상 제작을 응원하는 순수한 팬심에서, 
전체 방송 중 하이라이트로 예상되는 구간들을 임의로 추려본 가편집 데이터입니다.

일체의 상업적 대가나 조건을 요구하지 않으며, 부족한 결과물이지만 혹시라도 
편집 작업에 조금이나마 보탬이 될 수 있을까 하여 조심스레 공유해 드립니다. 
작업하시는 방식에 맞으신다면 편하게 참고해 주시고, 그렇지 않다면 
가볍게 넘겨주셔도 무방합니다.

--------------------------------------------------------------------------------
 📁 제공 파일 구성 및 참고 사항
--------------------------------------------------------------------------------

1. 🎞️ [가편집 타임라인 (60fps 메인)]
   - 파일명: *.xml
   - 설명: 프리미어 프로, 파이널컷 프로, 다빈치 리졸브 등에서 불러올 수 있는 프로젝트 파일입니다.
   - 참고: 오디오 크기(Peak) 등을 감지해 임의로 컷을 나누어 두었습니다. 
     클립 이름에 표시된 Peak 수치가 높을수록 텐션이 높은 구간일 확률이 있으니, 
     대략적인 포인트를 찾으실 때 가벼운 지표 정도로 참고해 주시면 좋을 것 같습니다.

2. 💬 [공용 초벌 자막 파일]
   - 파일명: *.srt
   - 설명: 가편집 구간의 음성 타이밍에 맞추어 임시로 생성해 본 초벌 자막입니다.
   - 참고: 여러 목소리가 겹치거나 게임 용어가 섞여 있어 텍스트 오타나 인식 오류가 꽤 많습니다. 
     다만 자막이 나오고 들어가는 타이밍(싱크)은 얼추 맞춰져 있으니, 
     텍스트만 덮어쓰며 수정하시는 쪽으로 활용해 보시는 것도 조심스레 제안해 봅니다.

--------------------------------------------------------------------------------
 💡 편집 프로그램 불러오기 관련 참고 사항 (동영상 연결 오류 시)
--------------------------------------------------------------------------------

편집 프로그램에서 XML 파일을 불러오실 때, 간혹 원본 영상을 제대로 인식하지 못하는 
경우가 있어 번거로우시겠지만 아래 방법들을 참고해 주시면 감사하겠습니다.

① 편집하실 원본 영상의 파일명을 다운로드하신 폴더명(날짜+방송 제목)과 동일하게 
   변경해 주시면 인식이 수월합니다.
② 가급적 XML 파일과 동영상 원본 파일은 같은 폴더 위치에 함께 두시기를 권장합니다.
③ 위 과정 후에도 영상을 인식하지 못한다면, 프로그램 내에서 영상 파일의 위치 경로
   (Link Media 등)를 수동으로 한 번만 다시 지정해 주시면 정상적으로 불러와집니다.

--------------------------------------------------------------------------------
 🔒 클라우드 드라이브 보관 안내
--------------------------------------------------------------------------------
* 본 폴더의 파일들은 구글 드라이브 용량 관리를 위해 업로드일 기준 [14일~30일] 동안 
  보관된 후 순차적으로 정리될 예정입니다. 혹시 필요하신 파일이 있다면 기한 내에 
  미리 다운로드해 두시기를 부탁드립니다.

모쪼록 작게나마 도움이 되었으면 좋겠습니다. 늘 응원합니다!
================================================================================
"""


def get_channel_marker_dir(channel_name: str) -> Path:
    """Returns and ensures existence of the base markers directory for a given channel."""
    if (
        not channel_name
        or "자동 감지" in channel_name
        or "본인 스타일" in channel_name
        or "수집된 채널" in channel_name
        or channel_name == "DefaultChannel"
    ):
        clean_channel = "미지정_스트리머"
    else:
        # Strip emoji manually just in case
        c = (
            channel_name.replace("🤖", "")
            .replace("🧬", "")
            .replace("스타일 (투트랙 AI)", "")
            .strip()
        )
        clean_channel = sanitize_filename(c, max_length=30, fallback="미지정_스트리머")
        if not clean_channel or clean_channel in (
            "[자동 감지] 분석 대상 스트리머 본인 스타일 (기본)",
            "DefaultChannel",
        ):
            clean_channel = "미지정_스트리머"

    p = config.base_dir / "markers" / clean_channel
    p.mkdir(parents=True, exist_ok=True)
    return p


def format_duration_kr(seconds: float) -> str:
    """Formats duration in seconds into human-readable Korean string."""
    sec = int(max(0.0, seconds))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60

    if h > 0:
        return f"{h}시간 {m}분 {s}초" if s > 0 else f"{h}시간 {m}분"
    elif m > 0:
        return f"{m}분 {s}초"
    else:
        return f"{s}초"


def format_time_hhmmss(seconds: float) -> str:
    """Convert seconds to HH:MM:SS string format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


STEALTH_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


