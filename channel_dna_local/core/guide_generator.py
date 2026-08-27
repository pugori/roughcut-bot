"""Studio-style Guide Document Generator for Rough Cut & Subtitle Packages.

Clean, concise, and direct corporate memo format explaining usage instructions.
"""

from pathlib import Path


class GuideGenerator:
    """Generates a clean, factual, and restrained guide document for rough cuts and subtitles."""

    @staticmethod
    def generate_guide_text(
        vod_title: str = "",
        vod_date: str = "",
        total_markers: int = 0,
        total_duration_str: str = "",
    ) -> str:
        clean_title = vod_title or "치지직 다시보기"
        clean_date = vod_date or "미지정"
        recommended_video_name = f"{clean_date}_{clean_title}.mp4"

        text = f"""[방송 정보]
- 제목: {clean_title}
- 일시: {clean_date}

[중요: 원본 영상 파일명 설정]
편집할 원본 영상(mp4)의 이름을 아래와 동일하게 변경해야 편집기에서 자동 인식됩니다.
👉 권장 파일명: {recommended_video_name}

[파일 구성]
- Solo (XML): 유튜브 개인 방송 분석을 바탕으로 생성된 파일
- Collab (XML): 유튜브 합방 분석을 바탕으로 생성된 파일
- 자막 (SRT)

[사용 방법]
1. 원본 영상(mp4) 이름을 위의 권장 파일명과 동일하게 변경합니다.
2. 영상과 전달된 파일들을 같은 폴더에 함께 배치합니다.
3. 영상 편집 프로그램에서 해당 XML 파일을 불러옵니다.
4. 타임라인 위에 SRT 자막 파일을 적용합니다.
"""
        return text

    @classmethod
    def save_guide_to_package(
        cls,
        package_dir: Path,
        vod_title: str = "",
        vod_date: str = "",
        total_markers: int = 0,
        total_duration_str: str = "",
    ) -> Path:
        """Saves the guide text file into the target package directory."""
        package_dir.mkdir(parents=True, exist_ok=True)
        file_path = package_dir / "가이드.txt"
        content = cls.generate_guide_text(
            vod_title=vod_title,
            vod_date=vod_date,
            total_markers=total_markers,
            total_duration_str=total_duration_str,
        )
        file_path.write_text(content, encoding="utf-8")
        return file_path
