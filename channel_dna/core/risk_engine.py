"""Risk Engine & Free Issue DB Collector module.
Collects community/wiki issue keywords for 0 cost (no paid AI API) and matches them against STT subtitles.
"""

from channel_dna.core.logger import get_logger

_logger = get_logger(__name__)

import re
import sqlite3
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from channel_dna.core.utils import format_time_hhmmss


@dataclass
class IssueMatchItem:
    timecode: str
    start_sec: float
    end_sec: float
    keyword: str
    spoken_sentence: str
    origin_context: str
    category: str


# Initial Permanent Seed DB (영구 보관용 핵심 이슈/유래 사전)
PERMANENT_SEED_KEYWORDS = [
    {
        "keyword": "운지",
        "category": "특정 커뮤니티 비하 용어",
        "origin_context": "특정 온라인 커뮤니티에서 특정 인물의 사망 사건을 조롱하고 비하하기 위해 만들어진 은어로, 방송 및 미디어에서 금기시되는 표현입니다.",
    },
    {
        "keyword": "이기야",
        "category": "특정 커뮤니티 비하 용어",
        "origin_context": "특정 인터넷 커뮤니티에서 사투리를 변형하여 조롱성 어조로 사용하기 시작한 억지 유행어로 알려져 있습니다.",
    },
    {
        "keyword": "삼일한",
        "category": "특정 집단 비하 용어",
        "origin_context": "온라인 커뮤니티에서 유래된 여성 혐오 및 폭력 조장 은어로, 심각한 논란을 일으키는 표현입니다.",
    },
    {
        "keyword": "한남",
        "category": "특정 집단 비하 용어",
        "origin_context": "남성 전체를 비하하고 멸칭하는 용도로 온라인 커뮤니티에서 파생된 표현입니다.",
    },
    {
        "keyword": "보이루",
        "category": "과거 논란 유행어",
        "origin_context": "유튜버의 인사말이었으나 온라인 갈등 및 법적 공방 과정에서 왜곡되어 젠더 갈등 이슈로 부각되었던 단어입니다.",
    },
    {
        "keyword": "오조오억",
        "category": "젠더 갈등 논란 용어",
        "origin_context": "단순 과장 수치 표현에서 출발했으나 특정 커뮤니티의 남성 혐오 맥락과 결부되어 게임/광고계에서 연쇄 수정 논란이 있었던 표현입니다.",
    },
    {
        "keyword": "허버허버",
        "category": "젠더 갈등 논란 용어",
        "origin_context": "음식을 급하게 먹는 모습을 묘사한 신조어였으나 남성 비하 뉘앙스로 온라인 갈등이 발생하여 방송계에서 자막 삭제 이력이 있습니다.",
    },
    {
        "keyword": "퐁퐁남",
        "category": "온라인 밈 / 갈등 용어",
        "origin_context": "결혼 생활 및 경제권 갈등과 관련하여 특정 세대 및 계층을 조롱하는 뉘앙스로 온라인 커뮤니티에서 유행한 신조어입니다.",
    },
    {
        "keyword": "설거지론",
        "category": "온라인 밈 / 갈등 용어",
        "origin_context": "온라인 커뮤니티에서 남녀 관계 및 결혼 문화를 자조적이고 비하적으로 해석하며 유행한 담론입니다.",
    },
    {
        "keyword": "누칼협",
        "category": "온라인 유행어",
        "origin_context": "'누가 칼 들고 협박함?'의 줄임말로, 상대방의 피해나 불만을 조롱하고 책임을 회피하는 냉소적 인터넷 밈입니다.",
    },
    {
        "keyword": "알빠노",
        "category": "온라인 유행어",
        "origin_context": "'알 바 아니다'와 특정 커뮤니티 어투가 결합된 신조어로, 무관심과 조롱의 뉘앙스를 내포하고 있습니다.",
    },
    {
        "keyword": "중꺾마",
        "category": "인터넷 유행어",
        "origin_context": "'중요한 것은 꺾이지 않는 마음'의 줄임말로, 롤드컵에서 유래하여 널리 쓰이는 대중적 유행어입니다.",
    },
]


class IssueDBCollector:
    """Free Web Scraper for Community & Wiki Issue Keywords (0 API Cost)."""

    def __init__(self, db_path: Path | None = None):
        from channel_dna.config import config

        self.db_path = Path(db_path) if db_path else config.default_db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS issue_keywords (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT UNIQUE NOT NULL,
                        category TEXT NOT NULL,
                        origin_context TEXT NOT NULL,
                        source TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                count = conn.execute("SELECT COUNT(*) FROM issue_keywords").fetchone()[
                    0
                ]
                if count == 0:
                    for item in PERMANENT_SEED_KEYWORDS:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO issue_keywords (keyword, category, origin_context, source)
                            VALUES (?, ?, ?, 'PermanentSeed')
                        """,
                            (item["keyword"], item["category"], item["origin_context"]),
                        )
                    conn.commit()
        finally:
            conn.close()

    def collect_from_web(self, progress_cb=None) -> int:
        """User manually clicks 'Start Collection' to gather fresh keywords (Free, No AI API)."""
        new_count = 0
        if progress_cb:
            progress_cb(
                "시작", 0.1, "공개 위키 및 커뮤니티 신조어 데이터 수집 준비 중..."
            )

        # 1. Permanent Seed Sync
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                for item in PERMANENT_SEED_KEYWORDS:
                    cur = conn.execute(
                        """
                        INSERT OR IGNORE INTO issue_keywords (keyword, category, origin_context, source)
                        VALUES (?, ?, ?, 'PermanentSeed')
                    """,
                        (item["keyword"], item["category"], item["origin_context"]),
                    )
                    if cur.rowcount > 0:
                        new_count += 1
                conn.commit()
        finally:
            conn.close()

        if progress_cb:
            progress_cb(
                "위키 수집", 0.4, "공개 웹 사전 및 온라인 신조어 색인 파싱 중..."
            )

        # 2. Free Web Scraper (NamuWiki / Wiki Mirror / Community Neologism Index)
        try:
            url = "https://ko.wikipedia.org/wiki/%EB%8C%80%ED%95%9C%EB%AF%BC%EA%B5%AD%EC%9D%98_%EC%9D%B8%ED%84%B0%EB%84%B7_%EC%8B%A0%EC%A1%B0%EC%96%B4_%EB%AA%A9%EB%A1%9D"
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                html = response.read().decode("utf-8")
                soup = BeautifulSoup(html, "html.parser")

                conn = sqlite3.connect(self.db_path)
                try:
                    with conn:
                        for li in soup.find_all("li"):
                            text = li.get_text()
                            if " : " in text or " - " in text:
                                parts = re.split(r" : | - ", text, maxsplit=1)
                                kw = parts[0].strip().replace('"', "").replace("'", "")
                                desc = (
                                    parts[1].strip()
                                    if len(parts) > 1
                                    else "온라인 인터넷 신조어"
                                )
                                if 2 <= len(kw) <= 15 and len(desc) > 5:
                                    cur = conn.execute(
                                        """
                                        INSERT OR IGNORE INTO issue_keywords (keyword, category, origin_context, source)
                                        VALUES (?, '온라인 신조어/유행어', ?, 'Wikipedia')
                                    """,
                                        (kw, desc),
                                    )
                                    if cur.rowcount > 0:
                                        new_count += 1
                        conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            _logger.debug("Silenced exception: %s", e)

        if progress_cb:
            progress_cb("완료", 1.0, "이슈 DB 갱신 완료")

        return new_count

    def get_all_keywords(self) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT keyword, category, origin_context FROM issue_keywords"
                ).fetchall()
                return [dict(r) for r in rows]
        finally:
            conn.close()


class RiskEngine:
    """Matches speech subtitles with issue/origin knowledge database."""

    def __init__(self, collector: IssueDBCollector):
        self.collector = collector

    def inspect_subtitles(self, subtitles: list[Any]) -> list[IssueMatchItem]:
        """Scans subtitles and returns matched issue items with surrounding context."""
        keywords_db = self.collector.get_all_keywords()
        if not keywords_db:
            return []

        matched_results: list[IssueMatchItem] = []
        seen_matches = set()

        for item in subtitles:
            text = getattr(item, "text", "")
            s_time = getattr(item, "start_sec", getattr(item, "start_time", 0.0))
            e_time = getattr(item, "end_sec", getattr(item, "end_time", 0.0))
            tc = getattr(item, "start_timecode", format_time_hhmmss(s_time))

            for kw_info in keywords_db:
                kw = kw_info["keyword"]
                if kw in text:
                    match_key = (tc, kw)
                    if match_key not in seen_matches:
                        seen_matches.add(match_key)
                        matched_results.append(
                            IssueMatchItem(
                                timecode=tc,
                                start_sec=s_time,
                                end_sec=e_time,
                                keyword=kw,
                                spoken_sentence=text.strip(),
                                origin_context=kw_info["origin_context"],
                                category=kw_info["category"],
                            )
                        )

        return matched_results

