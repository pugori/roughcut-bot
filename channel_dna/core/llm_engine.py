"""Universal Local LLM Engine using Ollama (exaone3.5:7.8b) for Post-Production AI."""

import logging
import time

import requests

from channel_dna.core.models import ScanMarker
from channel_dna.core.subtitle_formatter import SubtitleItem
from channel_dna.core.utils import format_time_hhmmss

logger = logging.getLogger(__name__)


class LocalLLMEngine:
    _global_available_cache = None
    _global_last_check_time = 0.0

    def __init__(
        self, creative_model: str = "exaone3.5:7.8b", strict_model: str = "qwen3:8b"
    ):
        self.api_url = "http://localhost:11434/api/generate"
        self.creative_model = (
            creative_model  # Used for Naming and Descriptions (needs wit)
        )
        self.strict_model = (
            strict_model  # Used for Proofreading (needs strict adherence)
        )

    @classmethod
    def is_available(cls) -> bool:
        now = time.time()
        if (
            cls._global_available_cache is not None
            and (now - cls._global_last_check_time) < 60.0
        ):
            return cls._global_available_cache
        try:
            import socket

            with socket.create_connection(("127.0.0.1", 11434), timeout=0.05):
                cls._global_available_cache = True
        except Exception:
            cls._global_available_cache = False
        cls._global_last_check_time = now
        return cls._global_available_cache

    def _generate(self, prompt: str, model_name: str, system: str = "") -> str:
        try:
            payload = {"model": model_name, "prompt": prompt, "stream": False}
            if system:
                payload["system"] = system

            resp = requests.post(self.api_url, json=payload, timeout=30.0)
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
        except Exception as e:
            logger.error(f"[LLM Error] {e}", exc_info=True)
        return ""

    def extract_dynamic_vocabulary(self, title: str, chat_context: str = "") -> str:
        """Dynamically extracts game terms and proper nouns from title and chat to feed Whisper RAG."""
        if not self.is_available():
            return ""

        prompt = (
            f"방송 제목: {title}\n"
            f"최근 시청자 채팅: {chat_context if chat_context else '없음'}\n\n"
            f"위 방송 제목과 채팅을 보고, 이 방송에서 자주 쓰일 것 같은 '고유명사(스트리머 이름, 게임 챔피언, 아이템 이름, 유행어)' 10~15개를 유추해서 쉼표로만 구분해서 나열해.\n"
            f"예시: 페이커, 롤, 가렌, 바론, 성수, 억까, 뇌절, 트롤, 혜자, 뉴비\n"
            f"반드시 부연 설명 없이 쉼표로 구분된 단어들만 출력해."
        )

        system = (
            "당신은 게임 용어사전 추출기입니다. 단어들만 쉼표로 구분해서 출력하세요."
        )

        res = self._generate(prompt, model_name=self.creative_model, system=system)
        if res:
            # Clean up the response (remove any markdown or conversational fluff)
            res = res.replace("```", "").replace("\n", ",")
            words = [w.strip() for w in res.split(",") if len(w.strip()) >= 2]
            return ", ".join(words[:15])
        return ""

    def proofread_subtitles(self, subtitles: list[SubtitleItem]) -> None:
        """[Speed Optimization] Bypassed.
        Whisper accuracy is high enough with our custom prompt, and processing 4,000+ lines
        via LLM causes token limit crashes and 5-minute freezes.
        """

    def generate_youtube_description(self, markers: list[ScanMarker], output_path: str):
        """Generates a complete YouTube video description with chapters based on the processed markers."""
        if not markers or not self.is_available():
            return

        timeline_info = "\n".join(
            [
                f"- {format_time_hhmmss(m.start_time)} : {m.label} ({m.reason})"
                for m in markers
            ]
        )

        prompt = (
            f"다음은 게임 방송 풀영상에서 추출한 하이라이트 타임라인입니다:\n\n{timeline_info}\n\n"
            f"이 내용을 바탕으로 유튜브 풀영상 업로드 시 '설명란'에 복사해서 붙여넣을 수 있는 "
            f"친근하고 재밌는 소개글과 챕터(타임스탬프)를 작성해 주세요.\n"
            f"주의사항: 유튜브 챕터 인식 조건에 맞게 작성해야 합니다.\n"
            f"1. 챕터 리스트의 맨 처음은 반드시 '00:00 시작' 으로 시작할 것.\n"
            f"2. 각 챕터는 최소 10초 이상 간격이 나도록 할 것.\n"
            f"3. 시간 형식은 MM:SS 형태로 적을 것."
        )

        system = "당신은 유명 유튜버의 전담 편집자입니다. 친근한 말투(해요체)로 유튜브 더보기란(설명란)을 작성하세요."

        res = self._generate(prompt, model_name=self.creative_model, system=system)
        if res:
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("=== ChannelDNA 자동 생성 유튜브 더보기란 ===\n\n")
                    f.write(res)
            except OSError as e:
                print(f"Error saving YouTube description: {e}")

    def classify_youtube_metadata_llm(
        self, title: str, description: str, tags: list[str]
    ) -> str:
        """Classify if a video is 'solo' or 'collab' using semantic understanding of gamer slang."""
        if not self.is_available():
            return "solo"  # Fallback

        tags_str = ", ".join(tags) if tags else "없음"
        desc_snippet = description[:500] if description else "없음"

        prompt = (
            f"다음은 게임/인터넷 방송 유튜버의 영상 정보입니다.\n"
            f"- 영상 제목: {title}\n"
            f"- 태그: {tags_str}\n"
            f"- 설명글 일부: {desc_snippet}\n\n"
            f"이 영상이 스트리머 혼자 진행하는 방송(솔로/영도/소통 등)인지, 아니면 타인과 함께 진행하는 합방/멀티플레이(크루, 내전, 스쿼드, 디코 참여 등)인지 판별하세요.\n"
            f"주의: 단순히 게임에 매칭된 랜덤 팀원이 아니라, 방송인이나 지인과 의도적으로 함께 진행한 경우만 'collab'입니다.\n"
            f"답변은 오직 'solo' 또는 'collab' 중 하나만 출력하세요."
        )

        res = self._generate(
            prompt,
            model_name=self.strict_model,
            system="너는 종합 게임 방송 트렌드를 완벽하게 이해하는 데이터 분류기야. 부연 설명 없이 오직 solo 또는 collab 이라는 단어만 출력해.",
        )

        ans = res.strip().lower()
        if "collab" in ans:
            return "collab"
        return "solo"


# Backward compatibility alias
LLMEngine = LocalLLMEngine

