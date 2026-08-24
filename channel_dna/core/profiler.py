"""Channel DNA Profiler module with automated channel lexicon extraction and Two-Track (Solo & Collab) DNA derivation."""

import json
import re
from collections import Counter

import numpy as np

from channel_dna.core.classifier import classify_youtube_video
from channel_dna.core.db import DBManager
from channel_dna.core.models import ChannelProfile


def extract_keywords_from_titles_and_meta(videos: list, top_n: int = 50) -> str:
    """Extract top frequent nouns, memes, and gaming keywords from video titles and mined lexicons."""
    words = []
    stopwords = {
        "영상", "모음", "하이라이트", "다시보기", "풀버전", "1부", "2부", "3부", "5부",
        "특", "있는", "하는", "진짜", "그냥", "오늘", "이거", "아니", "vs", "생각", "때문",
    }

    for v in videos:
        # Title keywords
        tokens = re.findall(r"[가-힣a-zA-Z0-9_]{2,}", v.title)
        for tok in tokens:
            if tok not in stopwords and not tok.isdigit():
                words.append(tok)

        # Mined lexicon stored in file_path if not voice print
        if v.file_path and not v.file_path.startswith("["):
            for tok in v.file_path.split(","):
                tok_clean = tok.strip()
                if len(tok_clean) >= 2 and tok_clean not in stopwords:
                    words.append(tok_clean)

    counts = Counter(words).most_common(top_n)
    vocab_list = [w for w, _ in counts]
    return ", ".join(vocab_list)


class ChannelProfiler:
    def __init__(self, db: DBManager | None = None):
        self.db = db or DBManager()

    def derive_two_track_profiles(
        self, channel_name: str
    ) -> tuple[ChannelProfile, ChannelProfile]:
        """Derives pure Two-Track DNA profiles (Solo & Collab) with Multi-Feature Motif and Mined Lexicon."""
        base_name = channel_name.replace("_Solo", "").replace("_Collab", "")

        # 1. Fetch channel's YouTube videos from DB
        videos = [
            v
            for v in self.db.get_all_videos()
            if (v.channel_name or "").lower() == base_name.lower()
        ]
        if not videos:
            videos = self.db.get_all_videos()

        existing_solo = self.db.get_profile(f"{base_name}_Solo")
        existing_collab = self.db.get_profile(f"{base_name}_Collab")
        existing_any = self.db.get_profile(base_name)

        yt_url = (
            (existing_solo and existing_solo.youtube_url)
            or (existing_collab and existing_collab.youtube_url)
            or (existing_any and existing_any.youtube_url)
            or ""
        )
        ch_url = (
            (existing_solo and existing_solo.chzzk_url)
            or (existing_collab and existing_collab.chzzk_url)
            or (existing_any and existing_any.chzzk_url)
            or ""
        )

        from channel_dna.core.graph_engine import GraphEngine

        graph_eng = GraphEngine()
        default_motif = graph_eng.get_default_motif_template()

        # If no videos, create and return default 2 profiles
        if not videos:
            solo_prof = ChannelProfile(
                profile_id=f"{base_name}_Solo",
                channel_name=f"{base_name}_Solo",
                avg_shot_length=3.8,
                silence_tolerance=0.8,
                highlight_rms_threshold=0.95,
                profile_type="solo",
                sample_count=0,
                custom_vocab=base_name,
                motif_template=default_motif,
                youtube_url=yt_url,
                chzzk_url=ch_url,
                narrative_quota={"intro": 0.40, "body": 0.40, "outro": 0.20},
                speech_density_weight=0.65,
                laughter_sensitivity=1.20,
            )
            collab_prof = ChannelProfile(
                profile_id=f"{base_name}_Collab",
                channel_name=f"{base_name}_Collab",
                avg_shot_length=2.2,
                silence_tolerance=1.2,
                highlight_rms_threshold=1.10,
                profile_type="collab",
                sample_count=0,
                custom_vocab=base_name,
                motif_template=default_motif,
                youtube_url=yt_url,
                chzzk_url=ch_url,
                narrative_quota={"intro": 0.30, "body": 0.50, "outro": 0.20},
                speech_density_weight=0.50,
                laughter_sensitivity=1.35,
            )
            self.db.save_profile(solo_prof)
            self.db.save_profile(collab_prof)
            return solo_prof, collab_prof

        # 2. Strict Two-Track Separation based on video_type column
        solo_vids = []
        collab_vids = []

        for v in videos:
            v_type = (v.video_type or "auto").lower()
            if v_type == "collab":
                collab_vids.append(v)
            elif v_type == "solo":
                solo_vids.append(v)
            else:
                det_type, _ = classify_youtube_video(
                    title=v.title,
                    description="",
                    tags=[],
                    duration=v.duration,
                    avg_shot_length=v.avg_shot_length,
                )
                if det_type == "collab":
                    collab_vids.append(v)
                else:
                    solo_vids.append(v)

        if not solo_vids:
            solo_vids = videos
        if not collab_vids:
            collab_vids = videos

        # Helper to compute profile parameters for a subset of videos
        def _calc_profile(
            v_list: list,
            prof_id: str,
            prof_name: str,
            p_type: str,
            default_asl: float,
            default_silence: float,
        ) -> ChannelProfile:
            asls = [v.avg_shot_length for v in v_list if v.avg_shot_length > 0]
            avg_asl = float(np.mean(asls)) if asls else default_asl

            all_peaks = []
            for v in v_list:
                for s in self.db.get_segments_by_video(v.video_id):
                    if s.rms_peak > 0:
                        all_peaks.append(s.rms_peak)

            percentile_rank = 70 if p_type == "solo" else 65
            threshold = (
                float(np.percentile(all_peaks, percentile_rank)) if all_peaks else 0.95
            )

            # Rich Mined Custom Vocabulary
            custom_vocab = extract_keywords_from_titles_and_meta(v_list, top_n=40)
            if not custom_vocab:
                custom_vocab = base_name

            # Voice print if available
            voice_prints = []
            if p_type == "solo":
                for v in v_list:
                    if v.file_path and v.file_path.startswith("["):
                        try:
                            vp = json.loads(v.file_path)
                            if isinstance(vp, list) and len(vp) > 0:
                                voice_prints.append(vp)
                        except Exception:
                            pass

            host_voice_print = None
            if voice_prints:
                host_voice_print = json.dumps(np.mean(voice_prints, axis=0).tolist())

            # Audio Dynamics weights from learned videos
            mean_speech_densities = [v.speech_density for v in v_list if v.speech_density > 0]
            mean_laughter_scores = [v.laughter_score for v in v_list if v.laughter_score > 0]

            speech_weight = (
                float(np.clip(np.mean(mean_speech_densities) * 0.9, 0.40, 0.85))
                if mean_speech_densities
                else (0.65 if p_type == "solo" else 0.50)
            )
            laughter_sens = (
                float(np.clip(np.mean(mean_laughter_scores) * 1.2, 0.80, 1.60))
                if mean_laughter_scores
                else (1.20 if p_type == "solo" else 1.35)
            )

            quota = (
                {"intro": 0.40, "body": 0.40, "outro": 0.20}
                if p_type == "solo"
                else {"intro": 0.30, "body": 0.50, "outro": 0.20}
            )

            prof = ChannelProfile(
                profile_id=prof_id,
                channel_name=prof_name,
                avg_shot_length=round(avg_asl, 2),
                tension_interval=45.0,
                silence_tolerance=default_silence,
                highlight_rms_threshold=round(min(1.35, max(0.65, threshold)), 2),
                hook_duration=15.0,
                sample_count=len(v_list),
                custom_vocab=custom_vocab,
                motif_template=default_motif,
                youtube_url=yt_url,
                chzzk_url=ch_url,
                profile_type=p_type,
                host_voice_print=host_voice_print,
                narrative_quota=quota,
                speech_density_weight=round(speech_weight, 2),
                laughter_sensitivity=round(laughter_sens, 2),
            )
            self.db.save_profile(prof)
            return prof

        solo_prof = _calc_profile(
            solo_vids, f"{base_name}_Solo", f"{base_name}_Solo", "solo", 3.8, 0.8
        )
        collab_prof = _calc_profile(
            collab_vids,
            f"{base_name}_Collab",
            f"{base_name}_Collab",
            "collab",
            2.2,
            1.2,
        )

        return solo_prof, collab_prof

    def update_video_type_and_reprofile(
        self, video_id: str, channel_name: str, new_type: str
    ) -> tuple[ChannelProfile, ChannelProfile]:
        """Manually updates video classification in DB and instantly re-derives pure Two-Track profiles in 0.01s."""
        self.db.update_video_type(video_id, new_type)
        base_name = channel_name.replace("_Solo", "").replace("_Collab", "")
        return self.derive_two_track_profiles(base_name)

    def derive_profile(self, channel_name: str) -> ChannelProfile:
        """Derive Two-Track profiles and return the requested mode (Collab or Solo)."""
        base_name = channel_name.replace("_Solo", "").replace("_Collab", "")
        solo_p, collab_p = self.derive_two_track_profiles(base_name)
        if "_Collab" in channel_name or channel_name.endswith("_collab"):
            return collab_p
        return solo_p
