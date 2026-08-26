"""Director-Grade Multimodal VOD Timeline Scanner.
Fuses 1k~3.5k Vocal Formant Tension, 1-second Conversational Speech Density, Laughter Dynamics, and Time-Lag Compensated Chzzk Chat.
Optimized with Asymmetric Physical Boundary Padding (-0.25s Lead-in, +0.40s Lead-out), 0.60s Micro-gap Merging, and In-Memory Buffer Lifecycle Management.
"""

from channel_dna.core.logger import get_logger

_logger = get_logger(__name__)

import gc
import re
from pathlib import Path
from typing import Any

import numpy as np

from channel_dna.config import config
from channel_dna.core.audio_engine import AudioEngine
from channel_dna.core.chat_engine import ChzzkChatEngine
from channel_dna.core.graph_engine import GraphEngine
from channel_dna.core.models import ChannelProfile, ProgressCallback, ScanMarker


def detect_vod_chapters(
    times: np.ndarray, tension_values: np.ndarray
) -> list[tuple[float, float, str]]:
    """Detects major narrative chapters in a long VOD based on 3-stage temporal segmentation.
    [1부: 0~15%] 오프닝 & 캐릭터 세팅
    [2부: 15~80%] 본 게임 & 사건 전개
    [3부: 80~100%] 클라이맥스 & 결말
    """
    if len(times) == 0:
        return [(0.0, 0.0, "[1부] 전체 에피소드")]

    total_dur = float(times[-1])
    if total_dur < 1200.0:  # < 20 min VOD: Single continuous narrative
        return [(0.0, total_dur, "[1부] 전체 에피소드")]

    # Divide into 3 story chapters (Intro, Main Gameplay/Events, Climax/Outro)
    p1 = total_dur * 0.15
    p2 = total_dur * 0.80

    return [
        (0.0, p1, "[1부] 오프닝 & 캐릭터 세팅 (Intro/Setup)"),
        (p1, p2, "[2부] 본 게임 & 사건 전개 (Main/Progression)"),
        (p2, total_dur, "[3부] 클라이맥스 & 결말 (Climax/Ending)"),
    ]


def apply_time_lag_compensation(
    tension_curve: np.ndarray,
    chat_curve: np.ndarray,
    speech_density: np.ndarray,
    laughter_curve: np.ndarray,
    times: np.ndarray,
    fps: float = 1.0,
    mode: str = "solo",
    speech_weight: float = 0.65,
    laughter_sens: float = 1.20,
) -> np.ndarray:
    """Multi-Modal 4-Way Fusion (Tension + Speech Density + Laughter Dynamics + Time-Lagged Chat)."""
    n = len(tension_curve)

    # 1. Chat signal backward shift: Chat reaction happens 2.0 ~ 3.5s AFTER the incident
    shift_frames = int(2.5 * fps)
    shifted_chat = np.zeros_like(chat_curve)
    if shift_frames > 0 and len(chat_curve) > shift_frames:
        shifted_chat[:-shift_frames] = chat_curve[shift_frames:]
    else:
        shifted_chat = chat_curve

    # 2. Conversational Speech Density Boost (Captures non-shouting rapid dialogue/banter in 0~45m)
    density_boost = (
        np.maximum(0.0, (speech_density - 0.40)) * float(speech_weight) * 2.0
    )

    # 3. Laughter & Pitch Burst Boost
    laughter_boost = laughter_curve * float(laughter_sens) * 0.8

    # 4. Integrate all signals into fused director score
    base_signal = (tension_curve * 0.55) + density_boost + laughter_boost

    has_chat = np.any(shifted_chat > 0)
    if has_chat:
        if mode == "collab":
            fused = (base_signal * 0.60) + (shifted_chat * 0.40 * 1.5)
        else:
            fused = (base_signal * 0.80) + (shifted_chat * 0.20 * 1.2)
    else:
        fused = base_signal

    return fused.astype(np.float32)


def find_speech_silence_boundaries(
    samples: np.ndarray,
    start_sec: float,
    end_sec: float,
    sr: int = 16000,
    search_window_sec: float = 2.0,
    lead_in_sec: float = 0.15,
    lead_out_sec: float = 0.28,
) -> tuple[float, float]:
    """Snaps start and end times to natural speech silence boundaries with Asymmetric Acoustic Headroom.
    - Lead-in (-0.15s): Preserves plosive consonants (ㅂ, ㄷ, ㄱ, ㅍ, ㅌ, ㅊ) and speech intake breath.
    - Lead-out (+0.28s): Preserves trailing vowels and room reverb, eliminating pop noise without lingering.
    """
    total_sec = len(samples) / sr

    # 1. Search backward for start silence (Natural sentence beginning)
    search_start = max(0.0, start_sec - search_window_sec)
    s_idx = int(search_start * sr)
    e_idx = int(min(total_sec, start_sec + 0.3) * sr)

    snapped_start = start_sec
    if e_idx > s_idx:
        slice_s = samples[s_idx:e_idx]
        frame_len = int(sr * 0.04)  # 40ms frames
        energies = [
            np.mean(slice_s[i : i + frame_len] ** 2)
            for i in range(0, len(slice_s) - frame_len, frame_len)
        ]
        if energies:
            min_energy_idx = int(np.argmin(energies))
            snapped_start = search_start + (min_energy_idx * 0.04)

    # Apply Lead-in padding (-0.15s)
    final_start = max(0.0, snapped_start - lead_in_sec)

    # 2. Search forward for end silence (Natural sentence conclusion / exhale)
    search_end = min(total_sec, end_sec + search_window_sec)
    s_idx = int(max(0.0, end_sec - 0.3) * sr)
    e_idx = int(search_end * sr)

    snapped_end = end_sec
    if e_idx > s_idx:
        slice_e = samples[s_idx:e_idx]
        frame_len = int(sr * 0.04)
        energies = [
            np.mean(slice_e[i : i + frame_len] ** 2)
            for i in range(0, len(slice_e) - frame_len, frame_len)
        ]
        if energies:
            min_energy_idx = int(np.argmin(energies))
            snapped_end = (end_sec - 0.3) + (min_energy_idx * 0.04)

    # Apply Lead-out padding (+0.28s)
    final_end = min(total_sec, snapped_end + lead_out_sec)

    return max(0.0, final_start), min(
        total_sec, max(final_start + config.min_marker_duration, final_end)
    )


class VODScanner:
    def __init__(self, audio_engine: AudioEngine | None = None):
        self.audio_engine = audio_engine or AudioEngine()
        self.chat_engine = ChzzkChatEngine()
        self.graph_engine = GraphEngine()

    def scan(
        self,
        vod_path: str,
        profile: ChannelProfile,
        use_cache: bool = True,
        scan_mode: str = "solo",
        progress_cb: ProgressCallback | None = None,
        cancel_event: Any | None = None,
        expected_duration_sec: float | None = None,
        preloaded_audio: np.ndarray | None = None,
        preloaded_chats: list[dict[str, Any]] | None = None,
    ) -> list[ScanMarker]:
        """Director-Grade Multimodal Scanning with 4-Way Audio, Speech Density, Laughter & Chat Fusion."""
        file_id = Path(vod_path).stem
        times: np.ndarray | None = None
        tension_values: np.ndarray | None = None
        speech_density: np.ndarray | None = None
        laughter_curve: np.ndarray | None = None
        audio_samples: np.ndarray | None = None

        # 1. Load or Extract Audio
        if preloaded_audio is not None and len(preloaded_audio) > 0:
            audio_samples = preloaded_audio
        else:
            audio_samples = self.audio_engine.extract_audio_in_memory(
                vod_path,
                progress_cb=progress_cb,
                cancel_event=cancel_event,
                expected_duration_sec=expected_duration_sec,
            )
        self.last_audio_samples = audio_samples

        if cancel_event and cancel_event.is_set():
            return []

        if len(audio_samples) == 0:
            raise ValueError("오디오 스트림을 디코딩하지 못했습니다.")

        if progress_cb:
            progress_cb(
                "TensionCalc", 0.38, "보컬 포먼트 분리 및 발화 밀도·웃음 궤적 연산 중..."
            )

        times, tension_values = self.audio_engine.compute_sliding_tension(audio_samples)
        _, speech_density, laughter_curve = (
            self.audio_engine.compute_speech_density_and_laughter_curves(audio_samples)
        )

        # Align lengths if needed
        min_len = min(
            len(times), len(tension_values), len(speech_density), len(laughter_curve)
        )
        times = times[:min_len]
        tension_values = tension_values[:min_len]
        speech_density = speech_density[:min_len]
        laughter_curve = laughter_curve[:min_len]

        total_dur_sec = float(times[-1]) if len(times) > 0 else 0.0

        # 2. Extract Chzzk Chat Signal (Fast JSON Paging, ~2s)
        chat_curve = np.zeros_like(tension_values)
        match_no = re.search(r"(\d{6,10})", vod_path)
        video_no = match_no.group(1) if match_no else ""

        chats = preloaded_chats
        if chats is None and video_no and total_dur_sec > 0:
            try:
                chats = self.chat_engine.fetch_vod_chat_logs(
                    video_no, total_dur_sec, progress_cb
                )
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)

        if chats:
            try:
                chat_vel = self.chat_engine.compute_chat_velocity_curve(
                    chats, total_dur_sec, bin_size_sec=1.0
                )
                if len(chat_vel) > 0:
                    chat_curve = np.interp(
                        times, np.arange(len(chat_vel)), chat_vel
                    )
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)

        # 3. Two-Track Mode & Profile Resolution
        active_mode = "solo"
        if scan_mode == "collab" or (profile and profile.profile_type == "collab"):
            active_mode = "collab"

        active_profile = profile
        if profile and profile.channel_name:
            base_ch = profile.channel_name.replace("_Solo", "").replace("_Collab", "")
            target_profile_name = (
                f"{base_ch}_{'Collab' if active_mode == 'collab' else 'Solo'}"
            )
            try:
                from channel_dna.core.db import DBManager

                sub_p = DBManager().get_profile(target_profile_name)
                if sub_p:
                    active_profile = sub_p
            except Exception:
                pass

        if progress_cb:
            prof_label = active_profile.channel_name if active_profile else "양망두_Solo"
            progress_cb(
                "TwoTrackClassify",
                0.60,
                f"[VOD 성격 분석] {'👥 합방' if active_mode=='collab' else '🎯 솔로'} 가중치 모드 ➔ '{prof_label}' (ASL {active_profile.avg_shot_length if active_profile else 3.8}s) 스타일 적용",
            )

        # 4. Multi-Modal 4-Way Fusion
        if progress_cb:
            progress_cb(
                "TimeLagFusion",
                0.65,
                "오디오 텐션 + 발화 밀도 + 웃음/피치 + 실시간 채팅 4-Way 융합 중...",
            )

        time_step = float(times[1] - times[0]) if len(times) > 1 else 0.5
        calc_fps = 1.0 / max(0.01, time_step)
        fused_score = apply_time_lag_compensation(
            tension_curve=tension_values,
            chat_curve=chat_curve,
            speech_density=speech_density,
            laughter_curve=laughter_curve,
            times=times,
            fps=calc_fps,
            mode=active_mode,
            speech_weight=active_profile.speech_density_weight
            if active_profile
            else 0.65,
            laughter_sens=active_profile.laughter_sensitivity
            if active_profile
            else 1.20,
        )

        if progress_cb:
            progress_cb(
                "GraphMatching",
                0.82,
                "채널 고유 기승전결 파형 템플릿(32-pt 그래프 유사도) 초고속 C-JIT 매칭 중...",
            )

        # 5. Graph Pattern Matching with ASL & Threshold
        target_rms = (
            active_profile.highlight_rms_threshold
            if (active_profile and active_profile.highlight_rms_threshold)
            else (1.05 if active_mode == "collab" else 0.85)
        )
        asl_target = (
            active_profile.avg_shot_length
            if (active_profile and active_profile.avg_shot_length)
            else (2.4 if active_mode == "collab" else 3.8)
        )

        matched_episodes = self.graph_engine.find_graph_pattern_matches(
            times=times,
            tensions=fused_score,
            motif_template=active_profile.motif_template if active_profile else None,
            asl_sec=asl_target,
            rms_threshold=target_rms,
            min_shape_similarity=0.35,
        )

        # 5-B. Conversational Banter & Laughter Burst Detection
        dt = float(times[1] - times[0]) if len(times) > 1 else 0.5
        win_size = int(18.0 / dt)
        if len(speech_density) > win_size:
            from scipy.ndimage import uniform_filter1d

            smooth_density = uniform_filter1d(
                speech_density.astype(np.float64), size=win_size
            ).astype(np.float32)
            smooth_laughter = uniform_filter1d(
                laughter_curve.astype(np.float64), size=win_size
            ).astype(np.float32)

            banter_score = smooth_density * 1.5 + smooth_laughter * 1.0
            banter_peaks = np.where(banter_score > 1.25)[0]

            if len(banter_peaks) > 0:
                cur_grp = [banter_peaks[0]]
                for idx in banter_peaks[1:]:
                    if idx <= cur_grp[-1] + int(8.0 / dt):
                        cur_grp.append(idx)
                    else:
                        b_st = float(times[cur_grp[0]])
                        b_et = float(times[cur_grp[-1]])
                        if 10.0 <= (b_et - b_st) <= 90.0:
                            if not any(
                                (st - 5.0 <= b_st <= et + 5.0)
                                for st, et, _, _ in matched_episodes
                            ):
                                pk = float(
                                    np.max(fused_score[cur_grp[0] : cur_grp[-1] + 1])
                                )
                                matched_episodes.append((b_st, b_et, pk, 0.88))
                        cur_grp = [idx]
                if len(cur_grp) > 0:
                    b_st = float(times[cur_grp[0]])
                    b_et = float(times[cur_grp[-1]])
                    if 10.0 <= (b_et - b_st) <= 90.0:
                        if not any(
                            (st - 5.0 <= b_st <= et + 5.0)
                            for st, et, _, _ in matched_episodes
                        ):
                            pk = float(
                                np.max(fused_score[cur_grp[0] : cur_grp[-1] + 1])
                            )
                            matched_episodes.append((b_st, b_et, pk, 0.88))

        # 6. Detect Narrative Chapters
        chapters = detect_vod_chapters(times, tension_values)
        if progress_cb and len(chapters) > 1:
            chap_summary = " | ".join(
                f"{c[2].split()[0]} ({int((c[1] - c[0]) / 60)}분)" for c in chapters
            )
            progress_cb(
                "NarrativeChapters", 0.88, f"서사 챕터 자동 감지: {chap_summary}"
            )

        # 7. Apply VAD Silence Snapping with Asymmetric Padding (-0.25s Lead-in, +0.40s Lead-out)
        search_window = (
            active_profile.silence_tolerance
            if (active_profile and active_profile.silence_tolerance)
            else (3.5 if active_mode == "collab" else 2.0)
        )
        buffered_markers: list[ScanMarker] = []
        for st, et, peak_score, sim_score in matched_episodes:
            raw_buf_start = max(0.0, st - 2.5)
            raw_buf_end = (
                min(total_dur_sec, et + 3.0) if total_dur_sec > 0 else (et + 3.0)
            )

            # Reaction hold: Give 0.60s extra room after high-tension peaks (laughter/shouting) for visual reaction
            extra_lead_out = 0.60 if peak_score >= 3.2 else 0.28

            snapped_st, snapped_et = find_speech_silence_boundaries(
                audio_samples,
                raw_buf_start,
                raw_buf_end,
                sr=self.audio_engine.sr,
                search_window_sec=search_window,
                lead_in_sec=0.15,
                lead_out_sec=extra_lead_out,
            )

            dur = snapped_et - snapped_st
            if dur >= config.min_marker_duration:
                chap_label = "에피소드"
                for c_st, c_et, c_name in chapters:
                    if c_st <= snapped_st < c_et:
                        chap_label = c_name.split()[0]
                        break

                buffered_markers.append(
                    ScanMarker(
                        start_time=round(snapped_st, 2),
                        end_time=round(snapped_et, 2),
                        duration=round(dur, 2),
                        peak_tension=round(float(peak_score), 2),
                        label=f"{chap_label} (Peak: {peak_score:.2f}, 유사도: {int(sim_score * 100)}%)",
                        reason=f"그래프 형상일치 {int(sim_score * 100)}% + 도파민피크 {peak_score:.2f}",
                    )
                )

        # 8. Dynamic Merging with 2.2s micro-gap (tighter cuts for fast-paced video editing)
        dynamic_max_duration = 75.0
        if active_profile and hasattr(active_profile, "tension_interval"):
            dynamic_max_duration = float(active_profile.tension_interval) * 1.8
            dynamic_max_duration = max(35.0, min(120.0, dynamic_max_duration))

        merged_markers = self._merge_overlapping_markers(
            buffered_markers, max_gap=2.2, max_duration=dynamic_max_duration
        )

        # 9. Essential Anchor Injections (Opening greeting within 0~5m & Outro within last 5m)
        anchor_markers: list[ScanMarker] = []
        has_intro_anchor = any(m.start_time < 180.0 for m in merged_markers)
        if not has_intro_anchor and total_dur_sec > 180.0:
            first_3m_idx = int(180.0 * calc_fps)
            if first_3m_idx < len(fused_score):
                best_intro_idx = int(np.argmax(fused_score[:first_3m_idx]))
                intro_t = float(times[best_intro_idx])
                s_st, s_et = find_speech_silence_boundaries(
                    audio_samples,
                    max(0.0, intro_t - 2.0),
                    intro_t + 22.0,
                    sr=self.audio_engine.sr,
                    search_window_sec=2.0,
                    lead_in_sec=0.25,
                    lead_out_sec=0.40,
                )
                if s_et - s_st >= 4.0:
                    anchor_markers.append(
                        ScanMarker(
                            start_time=round(s_st, 2),
                            end_time=round(s_et, 2),
                            duration=round(s_et - s_st, 2),
                            peak_tension=9.99,
                            label="[1부] 오프닝 인사 & 인트로 토크 (Intro Anchor)",
                            reason="방송 시작 필수 인트로 앵커 자동 보정",
                        )
                    )

        has_outro_anchor = any(
            m.end_time > (total_dur_sec - 180.0) for m in merged_markers
        )
        if not has_outro_anchor and total_dur_sec > 600.0:
            last_3m_idx = int((total_dur_sec - 180.0) * calc_fps)
            if last_3m_idx < len(fused_score):
                best_outro_idx = last_3m_idx + int(np.argmax(fused_score[last_3m_idx:]))
                outro_t = float(times[best_outro_idx])
                o_st, o_et = find_speech_silence_boundaries(
                    audio_samples,
                    max(0.0, outro_t - 5.0),
                    min(total_dur_sec, outro_t + 25.0),
                    sr=self.audio_engine.sr,
                    search_window_sec=2.0,
                    lead_in_sec=0.25,
                    lead_out_sec=0.40,
                )
                if o_et - o_st >= 4.0:
                    anchor_markers.append(
                        ScanMarker(
                            start_time=round(o_st, 2),
                            end_time=round(o_et, 2),
                            duration=round(o_et - o_st, 2),
                            peak_tension=9.98,
                            label="[3부] 방종 인사 & 엔딩 후열 (Outro Anchor)",
                            reason="방송 종료 필수 엔딩 앵커 자동 보정",
                        )
                    )

        if anchor_markers:
            merged_markers = self._merge_overlapping_markers(
                merged_markers + anchor_markers,
                max_gap=4.0,
                max_duration=dynamic_max_duration,
            )

        # 10. Narrative Balance with Pure Dynamic Extraction (No Artificial Caps)
        quota = (active_profile.narrative_quota if active_profile else None) or {
            "intro": 0.40,
            "body": 0.40,
            "outro": 0.20,
        }

        final_selected_markers: list[ScanMarker] = []
        if len(chapters) == 3:
            for idx, (c_st, c_et, _) in enumerate(chapters):
                c_markers = [m for m in merged_markers if c_st <= m.start_time < c_et]
                final_selected_markers.extend(c_markers)
        else:
            final_selected_markers = merged_markers

        # Sort chronologically
        merged_markers = sorted(final_selected_markers, key=lambda m: m.start_time)

        # Memory Lifecycle: release intermediate large signal arrays
        del tension_values
        del speech_density
        del laughter_curve
        del chat_curve
        del fused_score
        gc.collect()

        if progress_cb:
            progress_cb(
                "Complete",
                1.0,
                f"서사 균형 가편집 마커 {len(merged_markers)}개 생성 완료.",
            )

        return merged_markers

    def _merge_overlapping_markers(
        self,
        markers: list[ScanMarker],
        max_gap: float = 4.0,
        max_duration: float = 90.0,
    ) -> list[ScanMarker]:
        if not markers:
            return []

        sorted_m = sorted(markers, key=lambda m: m.start_time)
        merged = [sorted_m[0]]

        for current in sorted_m[1:]:
            prev = merged[-1]
            projected_duration = max(prev.end_time, current.end_time) - prev.start_time
            if (
                current.start_time <= prev.end_time + max_gap
                and projected_duration <= max_duration
            ):
                new_end = max(prev.end_time, current.end_time)
                prev.end_time = new_end
                prev.duration = round(new_end - prev.start_time, 2)
                prev.peak_tension = max(prev.peak_tension, current.peak_tension)
                prev.label = f"Highlight (Peak: {prev.peak_tension:.2f})"
            else:
                merged.append(current)

        return merged


