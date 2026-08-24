import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from channel_dna.core.pipeline import PipelineFacade

facade = PipelineFacade()
profile = facade.db.get_profile("Dokcake") or facade.profiler.derive_profile("Dokcake")
vod_url = "https://chzzk.naver.com/video/14668745"

markers = facade.scanner.scan(vod_url, profile, use_cache=True)

print("="*60, flush=True)
print("🏆 [그래프 유사도 매칭 검출 결과]", flush=True)
print("="*60, flush=True)
print(f"- 대상 방송: 26.08.12 심야공포괴담읽기2 (2시간 35분)", flush=True)
print(f"- 검출된 총 완결형 에피소드 마커: {len(markers)}개 (정예 선별)", flush=True)
avg_dur = sum(m.duration for m in markers) / max(1, len(markers)) if markers else 0.0
print(f"- 평균 에피소드 길이: {avg_dur:.1f}초 (기승전결 덩어리 묶음)", flush=True)

# Check episode around 00:23:00 ~ 00:35:00
target_episodes = [m for m in markers if 1350 <= m.start_time <= 2100]
print(f"\n[유튜브 실제 쓰인 괴담 에피소드 구간 (00:23:00 ~ 00:35:00)]", flush=True)
print(f"- 검출된 에피소드 마커: {len(target_episodes)}개", flush=True)

for idx, m in enumerate(sorted(target_episodes, key=lambda x: x.peak_tension, reverse=True)[:6], 1):
    print(f"{idx}. [{m.start_timecode} ~ {m.end_timecode}] (길이: {m.duration:.1f}초) | 텐션: {m.peak_tension:.2f} | {m.reason}", flush=True)
