import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
import time
import numpy as np

from channel_dna.core.pipeline import PipelineFacade
from channel_dna.core.models import ScanMarker

facade = PipelineFacade()
profile = facade.db.get_profile('Dokcake') or facade.profiler.derive_profile('Dokcake')
vod_url = 'https://chzzk.naver.com/video/14668745'

print("1. 치지직 VOD 전체 오디오 로드 중...")
audio_samples = facade.audio_engine.extract_audio_in_memory(vod_url)

test_markers = [
    ScanMarker(start_time=910.0, end_time=955.0, duration=45.0, peak_tension=3.5, label="1차 미스터리 괴담 썰"),
    ScanMarker(start_time=2550.0, end_time=2600.0, duration=50.0, peak_tension=3.4, label="후반부 괴담 결말 리액션")
]

print(f"\n2. 문장 단위 마커-자막 동기화 보정(Snap-to-Sentence) 실행 중...")
all_subtitles = facade.subtitle_engine.generate_subtitles_for_markers(
    audio_data=audio_samples,
    markers=test_markers,
    custom_vocab_prompt=profile.custom_vocab
)

print("\n" + "="*75)
print("📋 [문장 완결 보정 후 실측 자막 상세 결과]")
print("="*75)

for m_idx, m in enumerate(test_markers, 1):
    m_subs = [s for s in all_subtitles if (s.start_time >= m.start_time - 2.0) and (s.end_time <= m.end_time + 5.0)]
    print(f"\n🎯 [하이라이트 {m_idx}] {m.label} ({m.start_timecode} ~ {m.end_timecode})")
    print(f"   - 생성된 자막: {len(m_subs)}줄")
    for s in m_subs:
        dur = s.end_time - s.start_time
        print(f"   [{s.start_timecode} --> {s.end_timecode}] ({dur:.2f}s)")
        for line in s.text.split("\n"):
            print(f"     \"{line}\"")
