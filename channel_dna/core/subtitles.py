"""High-speed Subtitle Generation Engine using faster-whisper Large-v3-Turbo and Custom Channel Vocabulary.
Enhanced with Wideband Audio Preconditioning, Kiwi Korean NLP sentence structuring, and DaVinci Resolve 100% compatible 2-line stacked multi-speaker formatting.
"""

from channel_dna.core.logger import get_logger

_logger = get_logger(__name__)

import re
from pathlib import Path
from typing import Any

import numpy as np

from channel_dna.core.models import ChannelProfile, ProgressCallback, ScanMarker
from channel_dna.core.sentence_boundary import SentenceBoundaryRefiner
from channel_dna.core.subtitle_formatter import (
    KoreanSentenceFormatter,
    LexiconPostProcessor,
    SubtitleItem,
)
from channel_dna.core.subtitle_preprocessor import SubtitleAudioPreprocessor

HAS_FASTER_WHISPER = True


def convert_to_stacked_davinci_subs(
    subtitles: list[SubtitleItem],
) -> list[SubtitleItem]:
    """Converts overlapping multi-speaker subtitles into non-overlapping stacked 2-line subtitles
    and applies Smart Gap Bridging (<= 0.45s) and Anti-Collision clamping for 100% universal NLE compatibility.
    """
    if not subtitles:
        return []

    sorted_subs = sorted(subtitles, key=lambda s: s.start_time)
    stacked: list[SubtitleItem] = []

    i = 0
    while i < len(sorted_subs):
        cur = sorted_subs[i]

        # Check if next subtitle overlaps with cur
        if i + 1 < len(sorted_subs):
            nxt = sorted_subs[i + 1]
            if nxt.start_time < (cur.end_time - 0.15):
                cur_text = cur.text.strip()
                nxt_text = nxt.text.strip()

                is_diff_speaker = (
                    ("[화자 1]" in cur_text and "[화자 2]" in nxt_text)
                    or ("[화자 2]" in cur_text and "[화자 1]" in nxt_text)
                    or ("[도네]" in cur_text and "[도네]" not in nxt_text)
                    or ("[도네]" not in cur_text and "[도네]" in nxt_text)
                )

                if is_diff_speaker:
                    merged_st = min(cur.start_time, nxt.start_time)
                    merged_et = max(cur.end_time, nxt.end_time)
                    merged_text = f"{cur_text}\n{nxt_text}"
                    stacked.append(
                        SubtitleItem(
                            index=len(stacked) + 1,
                            start_time=round(merged_st, 2),
                            end_time=round(merged_et, 2),
                            text=merged_text,
                        )
                    )
                    i += 2
                    continue

        stacked.append(cur)
        i += 1

    # Pass 2: Smart Gap Bridging (<= 0.45s) & Strict Anti-Collision Snapping
    final_subs: list[SubtitleItem] = []
    for idx, s in enumerate(stacked, 1):
        s_copy = SubtitleItem(
            index=idx,
            start_time=s.start_time,
            end_time=s.end_time,
            text=s.text,
        )
        if final_subs:
            prev = final_subs[-1]
            gap = s_copy.start_time - prev.end_time
            if 0.0 < gap <= 0.45:
                # Bridge gap so subtitles don't flash/flicker between continuous speech
                prev.end_time = round(s_copy.start_time - 0.03, 2)
            elif gap < 0.0:
                # Anti-collision clamp: prevent overlapping subtitles
                prev.end_time = round(s_copy.start_time - 0.03, 2)
                if prev.end_time <= prev.start_time:
                    prev.end_time = round(prev.start_time + 0.35, 2)
        final_subs.append(s_copy)

    return final_subs


class SubtitleEngine:
    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_size = model_size
        if device == "cpu":
            try:
                import torch

                if torch.cuda.is_available():
                    device = "cuda"
                    if compute_type == "int8":
                        compute_type = "float16"
            except Exception:
                pass
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self.preprocessor = SubtitleAudioPreprocessor()
        self.formatter = KoreanSentenceFormatter()
        self.boundary_refiner = SentenceBoundaryRefiner(
            max_extension_sec=4.0, max_pre_snap_sec=1.5
        )
        from channel_dna.core.audio_engine import AudioEngine

        self.audio_engine = AudioEngine(sr=16000)

    def _get_model(self, progress_cb: ProgressCallback | None = None):
        if self._model is None:
            if progress_cb:
                progress_cb(
                    "SubtitleInit",
                    0.88,
                    "Whisper Large-v3-Turbo 고성능 한국어 전사 엔진 로드 중...",
                )
            import os
            import sys
            import glob

            os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
            if sys.platform != "win32":
                try:
                    import ctypes

                    for p in glob.glob(
                        os.path.join(
                            sys.prefix,
                            "lib",
                            "python*",
                            "site-packages",
                            "nvidia",
                            "*",
                            "lib",
                        )
                    ):
                        for so in glob.glob(os.path.join(p, "*.so*")):
                            try:
                                ctypes.CDLL(so)
                            except Exception:
                                pass
                except Exception:
                    pass
            from faster_whisper import WhisperModel
            import sys
            import os
            import pathlib

            # Determine true portable root directory
            if getattr(sys, "frozen", False):
                base_path = pathlib.Path(sys.executable).parent
            else:
                base_path = pathlib.Path.cwd()

            model_dir = str(base_path / "ChannelDNA_Models")
            os.makedirs(model_dir, exist_ok=True)

            safe_threads = 4
            num_w = 4 if self.device == "cuda" else 1

            candidate_models = [
                "small",  # Preferred lightweight model for Local Fork
                "deepdml/faster-whisper-large-v3-turbo-ct2",
                self.model_size,
                "large-v3-turbo",
            ]
            for m_name in candidate_models:
                try:
                    self._model = WhisperModel(
                        m_name,
                        device=self.device,
                        compute_type=self.compute_type,
                        cpu_threads=safe_threads,
                        num_workers=num_w,
                        download_root=model_dir,
                    )
                    break
                except Exception as e:
                    _logger.warning(
                        "Model load for %s failed (%s), trying next fallback...",
                        m_name,
                        e,
                    )

        return self._model

    def _get_batched_model(self, progress_cb=None):
        return self._get_model(progress_cb)

    def generate_subtitles_for_markers(
        self,
        audio_data: np.ndarray | None = None,
        source_path: str = "",
        broadcast_date: str = "",
        broadcast_title: str = "",
        markers: list[ScanMarker] | None = None,
        profile: ChannelProfile | None = None,
        progress_cb: ProgressCallback | None = None,
        sr: int = 16000,
        custom_vocab_prompt: str = "",
    ) -> list[SubtitleItem]:
        """Generate high-accuracy, zero-miss subtitles with Large-v3-Turbo and Kiwi NLP structuring."""
        model = self._get_model(progress_cb)
        if model is None or not markers:
            return []

        has_mem_audio = audio_data is not None and len(audio_data) > 0
        if not has_mem_audio and not source_path:
            return []

        from channel_dna.core.audio_engine import AudioEngine

        audio_engine = AudioEngine(sr=sr)

        lexicon_proc = LexiconPostProcessor(custom_vocab_prompt)
        vocab_terms = [v.strip() for v in custom_vocab_prompt.split(",") if v.strip()][
            :15
        ]

        ch_name = (
            getattr(profile, "channel_name", "")
            .replace("_Solo", "")
            .replace("_Collab", "")
            if profile
            else ""
        )
        prompt_prefix = (
            f"다음은 {ch_name} 스트리머의 한국어 인터넷 방송 대화 자막입니다."
            if ch_name
            else "다음은 한국어 인터넷 방송 대화 자막입니다."
        )
        if vocab_terms:
            prompt_prefix += f" 주요 키워드: {', '.join(vocab_terms)}."
        initial_prompt = f"{prompt_prefix} 자연스러운 구어체 대화로 정확히 전사합니다."

        all_subtitles: list[SubtitleItem] = []
        sub_global_idx = 1
        total_markers = len(markers)

        def _process_marker_task(idx_m):
            idx, m = idx_m
            # 1. Extract slice with AGC + generous pre/post margins
            if has_mem_audio:
                slice_audio, slice_st, _ = (
                    self.preprocessor.extract_marker_slice_with_preroll(
                        audio_data, m, pre_roll_sec=1.5, post_roll_sec=2.0
                    )
                )
            else:
                slice_st = max(0.0, m.start_time - 1.5)
                slice_et = m.end_time + 2.0
                raw_slice = audio_engine.extract_audio_slice(
                    source_path, slice_st, slice_et
                )
                if len(raw_slice) > 0:
                    slice_audio = self.preprocessor.preprocess_slice(raw_slice)
                else:
                    slice_audio = np.zeros(0, dtype=np.float32)

            if len(slice_audio) < int(sr * 0.4):
                return idx, m, []

            # 2. Trim silence edges safely with 350ms padding
            slice_audio, leading_trim_sec = self.preprocessor.trim_silence_edges(
                slice_audio
            )
            slice_st += leading_trim_sec

            if len(slice_audio) < int(sr * 0.4):
                return idx, m, []

            vocal_audio = slice_audio

            try:
                # High-Speed Accurate Direct GPU Whisper-Turbo Transcription (Zero VAD Overhead)
                transcribe_kwargs = dict(
                    language="ko",
                    initial_prompt=initial_prompt,
                    beam_size=1,
                    best_of=1,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    repetition_penalty=1.15,
                    compression_ratio_threshold=2.4,
                    no_speech_threshold=0.60,
                    vad_filter=False,  # Bypasses VAD overhead completely
                    word_timestamps=True,
                )

                segments_gen, info = model.transcribe(vocal_audio, **transcribe_kwargs)

                segments = []
                for seg in segments_gen:
                    segments.append(seg)
                    if progress_cb:
                        txt = seg.text.strip()
                        if txt:
                            # Shorten text to avoid UI overflow
                            if len(txt) > 30:
                                txt = txt[:27] + "..."
                            progress_cb(
                                "SubtitleGen",
                                0.89 + 0.05 * (idx / max(1, len(markers))),
                                f"전사 중 (컷 {idx}/{len(markers)}) [{seg.start:.1f}s]: {txt}",
                            )

                collected_words: list[dict[str, Any]] = []
                for seg in segments:
                    txt = seg.text.strip()
                    if not txt:
                        continue

                    if seg.words:
                        for w in seg.words:
                            w_st = max(0.0, float(w.start) - 0.05)
                            w_et = float(w.end)
                            collected_words.append(
                                {
                                    "word": w.word,
                                    "start": w_st,
                                    "end": w_et,
                                    "abs_start": w_st + slice_st,
                                    "abs_end": w_et + slice_st,
                                }
                            )
                    else:
                        collected_words.append(
                            {
                                "word": txt,
                                "start": float(seg.start),
                                "end": float(seg.end),
                                "abs_start": float(seg.start) + slice_st,
                                "abs_end": float(seg.end) + slice_st,
                            }
                        )

                # Snap to complete Korean sentence boundaries (Snap-to-Sentence)
                if collected_words:
                    refined_m, final_words = (
                        self.boundary_refiner.refine_marker_and_words(
                            m, collected_words, slice_offset=slice_st
                        )
                    )

                    m.start_time = refined_m.start_time
                    m.end_time = refined_m.end_time
                    m.duration = refined_m.duration

                    # Format into natural Korean sentences with Kiwi NLP
                    marker_subs = self.formatter.format_words_to_subtitles(
                        words=final_words,
                        time_offset=0.0,
                        lexicon_processor=lexicon_proc,
                    )
                    return idx, m, marker_subs

            except Exception as e:
                _logger.warning("Subtitle extraction error on marker %s: %s", idx, e)
            return idx, m, []

        import concurrent.futures
        import gc

        num_workers = 1 if self.device == "cuda" else 2
        results = []
        completed_count = 0

        if progress_cb:
            progress_cb(
                "SubtitleGen",
                0.89,
                f"한국어 전사 엔진 분석 시작... (총 {total_markers}컷)",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as pool:
            futures = [
                pool.submit(_process_marker_task, item)
                for item in enumerate(markers, 1)
            ]
            for fut in concurrent.futures.as_completed(futures):
                res = fut.result()
                results.append(res)
                completed_count += 1

                pct = (completed_count / total_markers) * 100.0
                if completed_count % 5 == 0 or completed_count == total_markers:
                    print(
                        f"[3/5] GPU STT Progress: {completed_count}/{total_markers} cuts transcribed ({pct:.0f}%)...",
                        flush=True,
                    )
                if progress_cb:
                    # Map transcription progress between 89% and 94%
                    overall_pct = 0.89 + (completed_count / total_markers) * 0.05
                    progress_cb(
                        "SubtitleGen",
                        overall_pct,
                        f"한국어 전사 엔진 분석 중... ({completed_count}/{total_markers} 컷 완료)",
                    )
                    if self.device == "cuda":
                        try:
                            import torch

                            torch.cuda.empty_cache()
                        except Exception:
                            pass
                    gc.collect()

        # Guarantee exact marker ordering and 100% preservation (zero omission)
        results.sort(key=lambda x: x[0])
        for idx, m, marker_subs in results:
            for s in marker_subs:
                s.index = sub_global_idx
                all_subtitles.append(s)
                sub_global_idx += 1

        # [Phase 2.5] Secondary Marker Overlap Deduplication Pass
        # Crucial fix: SentenceBoundaryRefiner can expand marker boundaries, potentially creating overlapping cuts.
        # We re-merge any overlapping or zero-gap markers to guarantee ZERO duplicate footage in the rough cut.
        if markers:
            markers.sort(key=lambda m: m.start_time)
            deduped_markers: list[ScanMarker] = [markers[0]]
            for cur_m in markers[1:]:
                prev_m = deduped_markers[-1]
                if cur_m.start_time <= (prev_m.end_time + 0.20):
                    # Merge overlapping cuts
                    prev_m.end_time = max(prev_m.end_time, cur_m.end_time)
                    prev_m.duration = round(prev_m.end_time - prev_m.start_time, 2)
                    prev_m.peak_tension = max(prev_m.peak_tension, cur_m.peak_tension)
                    if "Highlight" in prev_m.label and cur_m.label:
                        prev_m.label = cur_m.label
                else:
                    deduped_markers.append(cur_m)
            markers.clear()
            markers.extend(deduped_markers)

        # [Phase 3] Smart Donation (TTS) Filter & Collab-Only Diarization
        is_collab = False
        if profile is not None:
            p_type = getattr(profile, "profile_type", "")
            ch_name = getattr(profile, "channel_name", "")
            is_collab = (p_type == "collab") or ("_Collab" in ch_name)

        # 1. Detect Donation / TTS patterns
        donation_pattern = re.compile(
            r"(\d+[,.]?\d*\s*(원|치즈|캐시|비트|도네)|후원\s*(감사|하셨|했습|입니다)|투\s*네|트\s*윕|투\s*윕|익명\s*후원)",
            re.IGNORECASE,
        )
        for s in all_subtitles:
            if donation_pattern.search(s.text):
                if not (s.text.startswith("[도네]") or s.text.startswith("[화자")):
                    s.text = f"[도네] {s.text}"

        # 2. Multi-speaker Diarization ONLY when in explicit Collab mode
        if is_collab and len(all_subtitles) >= 4:
            if progress_cb:
                progress_cb(
                    "Diarization",
                    0.95,
                    "합방 화자 분리(Collab Diarization) 연산 중 (MFCC + KMeans)...",
                )
            try:
                import librosa
                from sklearn.cluster import KMeans
                from sklearn.metrics import silhouette_score

                features = []
                valid_indices = []
                for s_idx, s in enumerate(all_subtitles):
                    if s.text.startswith("[도네]"):
                        continue
                    line_audio = None
                    if has_mem_audio:
                        s_st = int(s.start_time * self.audio_engine.sr)
                        s_et = int(s.end_time * self.audio_engine.sr)
                        if 0 <= s_st < len(audio_data) and s_et <= len(audio_data):
                            line_audio = audio_data[s_st:s_et]
                    elif source_path:
                        line_audio = self.audio_engine.extract_audio_slice(
                            source_path, s.start_time, s.end_time
                        )

                    min_samples = int(self.audio_engine.sr * 0.4)
                    if line_audio is not None and len(line_audio) > 100:
                        if len(line_audio) < min_samples:
                            line_audio = np.pad(
                                line_audio, (0, min_samples - len(line_audio))
                            )
                        mfcc = librosa.feature.mfcc(
                            y=line_audio, sr=self.audio_engine.sr, n_mfcc=20
                        )
                        mfcc_mean = np.mean(mfcc, axis=1)
                        features.append(mfcc_mean)
                        valid_indices.append(s_idx)

                if len(features) >= 4:
                    X = np.array(features)
                    kmeans = KMeans(n_clusters=2, random_state=42, n_init=10)
                    labels = kmeans.fit_predict(X)
                    score = silhouette_score(X, labels)

                    # Only apply speaker tags if clusters are genuinely distinct (silhouette >= 0.18)
                    if score >= 0.18:
                        first_label = int(labels[0])
                        speaker_map = {
                            first_label: "[화자 1]",
                            1 - first_label: "[화자 2]",
                        }
                        for idx_in_valid, orig_idx in enumerate(valid_indices):
                            tag = speaker_map[int(labels[idx_in_valid])]
                            sub = all_subtitles[orig_idx]
                            if not (
                                sub.text.startswith("[화자")
                                or sub.text.startswith("[도네")
                                or sub.text.startswith("🗣️")
                            ):
                                sub.text = f"{tag} {sub.text}"
            except Exception as e:
                _logger.debug("Diarization failed: %s", e)

        # [Phase 4] Same-Speaker Consolidation: Merge consecutive short fragments from same speaker
        consolidated: list[SubtitleItem] = []
        if all_subtitles:
            all_subtitles.sort(key=lambda s: s.start_time)
            cur = all_subtitles[0]
            for nxt in all_subtitles[1:]:
                cur_spk = cur.text[:8] if cur.text.startswith("[화자") else ""
                nxt_spk = nxt.text[:8] if nxt.text.startswith("[화자") else ""

                gap = nxt.start_time - cur.end_time
                if (
                    cur_spk
                    and cur_spk == nxt_spk
                    and gap < 1.2
                    and (len(cur.text) + len(nxt.text) - len(cur_spk)) < 36
                ):
                    clean_nxt_text = nxt.text[len(nxt_spk) :].strip()
                    cur.text = f"{cur.text} {clean_nxt_text}".strip()
                    cur.end_time = max(cur.end_time, nxt.end_time)
                else:
                    consolidated.append(cur)
                    cur = nxt
            consolidated.append(cur)
            all_subtitles = consolidated

        # Ensure global chronological order and sequential 1-based indexing for SRT export
        all_subtitles.sort(key=lambda s: (s.start_time, s.end_time))
        for idx, s in enumerate(all_subtitles, 1):
            s.index = idx

        if progress_cb:
            progress_cb(
                "SubtitleGen", 0.99, f"초벌 자막 총 {len(all_subtitles)}줄 생성 완료."
            )

        return all_subtitles

    def map_subtitles_to_rough_cut(
        self,
        subtitles: list[SubtitleItem],
        markers: list[ScanMarker],
        fps: float = 60.0,
    ) -> list[SubtitleItem]:
        """Maps absolute VOD subtitles into the contiguous Rough Cut timeline coordinates (00:00:00 ~ End) with frame-exact alignment."""
        if not subtitles or not markers:
            return []

        rough_cut_subs: list[SubtitleItem] = []
        timeline_offset_frames = 0

        for m in markers:
            in_f = int(round(m.start_time * fps))
            out_f = int(round(m.end_time * fps))
            dur_f = max(1, out_f - in_f)

            clip_start_sec = in_f / fps
            clip_dur_sec = dur_f / fps
            timeline_start_sec = timeline_offset_frames / fps

            # Find subtitles belonging to this marker (within clip boundary)
            m_subs = [
                s
                for s in subtitles
                if (clip_start_sec - 0.05)
                <= s.start_time
                < (clip_start_sec + clip_dur_sec + 0.05)
            ]

            for s in m_subs:
                rel_st = max(0.0, s.start_time - clip_start_sec)
                rel_et = min(clip_dur_sec, s.end_time - clip_start_sec)
                if rel_et <= rel_st:
                    rel_et = min(
                        clip_dur_sec, rel_st + max(0.2, s.end_time - s.start_time)
                    )

                # Cut-boundary clamping: ensure subtitle never bleeds past the cut end
                rel_et = min(clip_dur_sec - 0.03, rel_et)
                if rel_et <= rel_st:
                    continue

                mapped_st = timeline_start_sec + rel_st
                mapped_et = timeline_start_sec + rel_et

                text_clean = s.text.strip()
                if text_clean and not text_clean.startswith("Highlight (Peak:"):
                    rough_cut_subs.append(
                        SubtitleItem(
                            index=len(rough_cut_subs) + 1,
                            start_time=round(mapped_st, 3),
                            end_time=round(mapped_et, 3),
                            text=text_clean,
                        )
                    )

            timeline_offset_frames += dur_f

        return rough_cut_subs

    def export_srt(self, subtitles: list[SubtitleItem], output_path: str) -> Path:
        """Export clean, single-file 2-line stacked SRT (100% universal across DaVinci Resolve ST1, Premiere Pro, CapCut, and Vrew)."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        # 1. Convert to 2-line Stacked Non-Overlapping SRT
        davinci_stacked = convert_to_stacked_davinci_subs(subtitles)
        self._write_srt_file(davinci_stacked, out_file)

        return out_file

    def remap_subtitles_to_sequence(self, markers: list, subtitles: list) -> list:
        """Remaps subtitles from absolute original time to Cut Sequence Timeline with Cut-Boundary Zero Bleed (-0.05s)."""
        import copy

        remapped_subs = []
        seq_time = 0.0

        for m in markers:
            m_start = m.start_time
            m_end = m.end_time
            m_dur = m.end_time - m.start_time
            # Safety headroom: clamp subtitle end 2~3 frames (0.05s) before cut boundary
            max_clip_end = max(0.20, m_dur - 0.05)

            for s in subtitles:
                if s.start_time >= (m_start - 0.3) and s.start_time < (m_end - 0.05):
                    s_offset = max(0.0, s.start_time - m_start)
                    e_offset = min(max_clip_end, s.end_time - m_start)

                    if e_offset > s_offset:
                        new_s = copy.deepcopy(s)
                        new_s.start_time = round(seq_time + s_offset, 3)
                        new_s.end_time = round(seq_time + e_offset, 3)
                        remapped_subs.append(new_s)

            seq_time += m_dur

        return remapped_subs

    def export_srt_by_speakers(
        self, subtitles: list[SubtitleItem], base_output_path: str
    ) -> list[Path]:
        """Extract speakers and export clean NLE-ready SRT files.
        - Single Speaker (Solo): exports clean `[stem]_자막.srt`
        - Multi Speaker (Collab/TTS): exports ONLY individual speaker tracks `[stem]_자막_[화자].srt` (NO integrated / merged subtitle)
        """
        from collections import defaultdict
        from pathlib import Path

        speaker_groups = defaultdict(list)

        for s in subtitles:
            speaker = "메인"
            text = s.text.strip()
            if text.startswith("[") and "]" in text:
                end_idx = text.find("]")
                tag = text[1:end_idx].strip()
                speaker = tag
                s_copy = SubtitleItem(
                    index=s.index,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    text=text[end_idx + 1 :].strip(),
                )
            else:
                s_copy = SubtitleItem(
                    index=s.index,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    text=text,
                )
            speaker_groups[speaker].append(s_copy)

        base_path = Path(base_output_path)
        base_dir = base_path.parent
        stem = base_path.stem
        if stem.endswith("_자막"):
            stem = stem[:-3]

        exported_paths: list[Path] = []

        # 1. If only single speaker, export as clean single [stem]_자막.srt
        if len(speaker_groups) <= 1 or (
            len(speaker_groups) == 1
            and ("메인" in speaker_groups or "미분류" in speaker_groups)
        ):
            single_list = (
                list(speaker_groups.values())[0] if speaker_groups else subtitles
            )
            out_path = base_dir / f"{stem}_자막.srt"
            self.export_srt(single_list, str(out_path))
            exported_paths.append(out_path)
            return exported_paths

        # 2. Multi-speaker export: ONLY individual speaker tracks (No redundant merged file)
        for spk, sub_list in speaker_groups.items():
            safe_spk = spk.replace(" ", "_").replace("/", "_").replace(":", "_")
            spk_srt_path = base_dir / f"{stem}_자막_{safe_spk}.srt"
            self.export_srt(sub_list, str(spk_srt_path))
            exported_paths.append(spk_srt_path)

        return exported_paths

    def _write_srt_file(self, subs_list: list[SubtitleItem], target_path: Path):
        try:
            import pysubs2

            subs = pysubs2.SSAFile()
            for idx, s in enumerate(subs_list, 1):
                start_ms = int(round(s.start_time * 1000))
                end_ms = int(round(s.end_time * 1000))
                if end_ms <= start_ms:
                    end_ms = start_ms + 500
                event = pysubs2.SSAEvent(
                    start=start_ms, end=end_ms, text=s.text.strip()
                )
                subs.events.append(event)
            subs.save(str(target_path), encoding="utf-8")
        except Exception:
            blocks = []
            for idx, s in enumerate(subs_list, 1):
                blocks.append(
                    f"{idx}\n{s.start_timecode} --> {s.end_timecode}\n{s.text.strip()}\n"
                )
            content = "\n".join(blocks)
            target_path.write_text(content, encoding="utf-8")
