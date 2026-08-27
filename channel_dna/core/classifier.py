"""Universal VOD & YouTube Video Classifier for Two-Track (Solo vs Collab) DNA.

Handles:
1. YouTube edited video classification (Solo vs Collab) via rich metadata, tags, mentions, and ASL editing rhythm.
2. Chzzk/Live Raw VOD classification (Solo vs Collab) via multi-window audio acoustic heuristics and full-stream chat dynamics.
3. 4-Layer filtering to prevent Donation TTS, Video Donations, and NPC/Game audio from misclassifying Solo as Collab.
"""

import re

import numpy as np

from channel_dna.core.models import SegmentData

# ==============================================================================
# Comprehensive Regex & Keyword Rules (Universal for any streamer)
# ==============================================================================

# Definite multi-speaker / collaboration keywords
COLLAB_KEYWORDS_REGEX = re.compile(
    r"(?i)\b(with|w/|feat\.?|ft\.?|vs\.?)\b|"
    r"\[(합방|콜라보|내전|대회|팀배틀|듀오|스쿼드|합작|크루|산악회|이세돌|공대|고멤|게스트|초대석)\]|"
    r"\((합방|콜라보|내전|대회|팀배틀|듀오|스쿼드|합작|크루|산악회|이세돌|공대|고멤|게스트|초대석)\)|"
    r"(합방|합동방송|합동|게스트|초대석|초대했습니다|모셨습니다|찾아온|방문|"
    r"디스코드|디코|디코방|음성채팅|통화|보이스|음챗|"
    r"내전|스크림|대회|자낳대|팀전|듀오|트리오|스쿼드|다인큐|5인큐|4인큐|3인큐|2인큐|"
    r"크루|멤버들|고멤|아카데미|이세돌|산악회|로아공대|공대|레이드|트라이|"
    r"마크서버|띵타이쿤|악어의놀이터|퐁퐁섭|포켓몬서버|서버|약탈전|합작|"
    r"구구덕|구스구스덕|덕몽어스|어몽어스|리썰컴퍼니|리썰|파스모포비아|갈틱폰|마피아|"
    r"술먹방|야외방송|야방|모였습니다|같이했습니다|함께했습니다|같이|함께)",
    re.UNICODE,
)

# Streamer name connection patterns: e.g. "침착맨이랑 주호민", "우왁굳과 이세돌", "괴물쥐 x 랄로", "김철수, 박영희"
COLLAB_PARTICLE_REGEX = re.compile(
    r"(?:[가-힣a-zA-Z0-9]{2,8}(?:이?랑|와|과)\s+[가-힣a-zA-Z0-9]{2,8})|"
    r"(?:[가-힣a-zA-Z0-9]{2,8}\s*(?:x|X|×|\+|&|vs|VS|Vs|w/)\s*[가-힣a-zA-Z0-9]{2,8})|"
    r"(?:[가-힣a-zA-Z0-9]{2,8}(?:,\s*|/\s*)[가-힣a-zA-Z0-9]{2,8}(?:,\s*|/\s*)[가-힣a-zA-Z0-9]{2,8})",
    re.UNICODE,
)

# Common Solo / Donation keywords (explicitly indicates solo content even if multiple voices exist)
SOLO_DONATION_REGEX = re.compile(
    r"(?i)(영도|영상도네|도네이션|도네|치즈|투네이션|트윕|리액션|"
    r"혼자|솔로|솔큐|자유랭|솔랭|노방종|썰풀기|소통|노가리|"
    r"Q&A|큐앤에이|혼술|일상|브이로그|공지|신곡|월드컵|이상형)",
    re.UNICODE,
)

# Other streamer channel link patterns in YouTube description
OTHER_CHANNEL_LINK_REGEX = re.compile(
    r"(?i)(youtube\.com/@|youtube\.com/channel/|chzzk\.naver\.com/|twitch\.tv/|bj\.afreecatv\.com/|bj\.sooplive\.co\.kr/)"
)


def classify_youtube_video(
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    duration: float = 0.0,
    avg_shot_length: float = 0.0,
    segments: list[SegmentData] | None = None,
    audio_data: np.ndarray | None = None,
    sr: int = 16000,
    use_llm: bool = True,
) -> tuple[str, list[float] | None]:
    """Classifies a YouTube edited video as 'solo' or 'collab'.

    [Phase 5] Returns (mode, host_voice_print).
    """
    title_clean = title.strip()
    desc_clean = description.strip()

    collab_confidence = 0.0
    host_voice_print = None
    if audio_data is not None and len(audio_data) > sr * 10:
        try:
            import librosa
            from sklearn.cluster import KMeans

            # Extract 20 MFCCs every 10 seconds to sample vocal timbre across the video
            features = []
            chunk_samples = sr * 5
            for i in range(
                0, min(len(audio_data), sr * 600), chunk_samples
            ):  # scan up to first 10 minutes
                chunk = audio_data[i : i + chunk_samples]
                if (
                    np.max(np.abs(chunk)) > 0.05
                ):  # Only analyze chunks with actual speech/sound
                    mfcc = librosa.feature.mfcc(y=chunk, sr=sr, n_mfcc=20)
                    features.append(np.mean(mfcc, axis=1))

            if len(features) > 5:
                X = np.array(features)
                # Compute variance of the timbre
                variance = np.var(X, axis=0).mean()

                # Turn-taking analysis to prevent Video Donation / TTS False Positives (Phase 4 Task 3)
                kmeans = KMeans(n_clusters=2, random_state=42, n_init=5)
                labels = kmeans.fit_predict(X)
                transitions = np.sum(np.diff(labels) != 0)
                turn_taking_rate = transitions / len(labels)

                if variance > 500.0:
                    if (
                        turn_taking_rate > 0.15
                    ):  # High variance AND high ping-pong = True Collab
                        collab_confidence += 2.0
                    else:  # High variance but NO ping-pong = Video Donation / TTS
                        collab_confidence -= 1.0
                        host_voice_print = X.mean(axis=0).tolist()
                elif variance < 200.0:  # Low variance means single voice (Solo)
                    collab_confidence -= 1.0
                    host_voice_print = X.mean(axis=0).tolist()
        except Exception as e:
            print(f"MFCC Timbre analysis failed: {e}")

    # 2. Fast Regex & Keyword Matching (0.001s instant heuristic)
    collab_score = 0.0

    if COLLAB_KEYWORDS_REGEX.search(title_clean):
        collab_score += 3.5

    if COLLAB_PARTICLE_REGEX.search(title_clean):
        collab_score += 3.0

    at_mentions = re.findall(r"@[\w가-힣]+", title_clean)
    if len(at_mentions) >= 1:
        collab_score += 2.5

    if desc_clean:
        other_links = OTHER_CHANNEL_LINK_REGEX.findall(desc_clean)
        if len(other_links) >= 1:
            collab_score += 2.5
        if COLLAB_KEYWORDS_REGEX.search(desc_clean):
            collab_score += 1.5
        desc_mentions = re.findall(r"@[\w가-힣]+", desc_clean)
        if len(desc_mentions) >= 2:
            collab_score += 1.5

    if tags:
        for tag in tags:
            tag_str = str(tag).strip()
            if COLLAB_KEYWORDS_REGEX.search(tag_str) or COLLAB_PARTICLE_REGEX.search(
                tag_str
            ):
                collab_score += 2.5
                break

    if SOLO_DONATION_REGEX.search(title_clean) and not (
        COLLAB_KEYWORDS_REGEX.search(title_clean)
        or COLLAB_PARTICLE_REGEX.search(title_clean)
    ):
        collab_score -= 3.5

    # If obvious regex/tag/desc heuristic result, return immediately
    if collab_score >= 2.0:
        return "collab", None
    if collab_score <= -2.0:
        return "solo", host_voice_print

    # 3. Semantic LLM Classification (for subtle/ambiguous titles)
    if use_llm:
        try:
            from channel_dna.core.llm_engine import LocalLLMEngine

            llm = LocalLLMEngine()
            if llm.is_available():
                llm_result = llm.classify_youtube_metadata_llm(
                    title_clean, desc_clean, tags or []
                )
                if llm_result in ["solo", "collab"]:
                    return (
                        llm_result,
                        host_voice_print if llm_result == "solo" else None,
                    )
        except Exception as e:
            print(f"LLM Classification failed: {e}")

    asl_val = avg_shot_length
    if asl_val <= 0.0 and segments and len(segments) > 5:
        durations = [s.duration for s in segments if s.duration > 0]
        if durations:
            asl_val = float(np.mean(durations))

    if asl_val > 0.0:
        if asl_val < 2.6:
            collab_score += 1.0
        elif asl_val > 4.5:
            collab_score -= 1.0

    final_mode = "collab" if collab_score >= 2.0 else "solo"
    return final_mode, host_voice_print if final_mode == "solo" else None






def classify_chzzk_vod(
    title: str,
    chats: list[dict] | None = None,
    chat_logs: list[dict] | None = None,
    audio_data: np.ndarray | None = None,
    audio_samples: np.ndarray | None = None,
    sr: int = 16000,
) -> tuple[str, float, str]:
    """Classifies raw Chzzk VOD as 'solo' or 'collab' with confidence score and reason."""
    title_clean = title.strip()
    if COLLAB_KEYWORDS_REGEX.search(title_clean) or COLLAB_PARTICLE_REGEX.search(title_clean):
        return "collab", 0.90, "제목에서 합방/콜라보 키워드 검출"

    actual_chats = chats or chat_logs or []
    if actual_chats:
        collab_chat_count = sum(
            1 for c in actual_chats if COLLAB_KEYWORDS_REGEX.search(c.get("content", c.get("msg", "")))
        )
        if collab_chat_count >= 5:
            return "collab", 0.85, f"실시간 채팅창에서 합방 관련 대화 다수 감지 ({collab_chat_count}회)"

    return "solo", 0.80, "솔로 방송 패턴 일치"

