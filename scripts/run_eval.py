import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
from dataclasses import dataclass
from channel_dna.core.pipeline import PipelineFacade

facade = PipelineFacade()
profile = facade.db.get_profile("Dokcake") or facade.profiler.derive_profile("Dokcake")

vod_url = "https://chzzk.naver.com/video/14668745"
yt_url = "https://youtu.be/tDFkVb5YiSU"

print("1. 치지직 VOD 마커 추출 중...")
markers = facade.scanner.scan(vod_url, profile, use_cache=True)
print(f"✓ 마커 {len(markers)}개 준비 완료.")

print("2. 유튜브 완성본 오디오 및 자막 추출 중...")
yt_audio = facade.audio_engine.extract_audio_in_memory(yt_url)
yt_dur = len(yt_audio) / 16000.0

@dataclass
class MockMarker:
    start_time: float
    end_time: float
    duration: float

yt_subs = facade.subtitle_engine.generate_subtitles_for_markers(
    audio_data=yt_audio,
    markers=[MockMarker(start_time=0.0, end_time=yt_dur, duration=yt_dur)],
    custom_vocab_prompt="독케익 공포 괴담"
)
print(f"✓ 유튜브 완성본 대사 {len(yt_subs)}줄 추출 완료.")

print("3. 원본 치지직 마커 구간 대사 추출 중...")
vod_audio = facade.audio_engine.extract_audio_in_memory(vod_url)
vod_subs = facade.subtitle_engine.generate_subtitles_for_markers(
    audio_data=vod_audio,
    markers=markers[:35],
    custom_vocab_prompt="독케익 공포 괴담"
)
print(f"✓ 원본 마커 구간 대사 {len(vod_subs)}줄 추출 완료.")

print("\n=======================================================")
print("4. 유튜브 편집본 컷 vs ChannelDNA 마커 1:1 대조 결과")
print("=======================================================")
hits = []
valid_yt = [y for y in yt_subs if len(y.text.strip()) >= 5]

for ys in valid_yt:
    yt_txt = ys.text.strip().replace(" ", "")
    for vs in vod_subs:
        vod_txt = vs.text.strip().replace(" ", "")
        if yt_txt in vod_txt or vod_txt in yt_txt or (len(yt_txt) >= 7 and yt_txt[:7] in vod_txt):
            hits.append((ys, vs))
            break

recall_pct = (len(hits) / max(1, len(valid_yt))) * 100

print(f"📊 [정량적 일치도 분석]")
print(f"- 유튜브 완성본 유효 대사 수: 총 {len(valid_yt)}문장")
print(f"- ChannelDNA 마커 내 적중 대사 수: 총 {len(hits)}문장")
print(f"🎯 최종 하이라이트 포착 정확도 (Recall): {recall_pct:.1f}%\n")

print("📌 [실제 1:1 일치 발언 매칭 샘플]")
for idx, (ys, vs) in enumerate(hits[:5], 1):
    h = int(vs.start_sec // 3600)
    m = int((vs.start_sec % 3600) // 60)
    s = int(vs.start_sec % 60)
    print(f"{idx}. 원본 치지직 타임코드 [{h:02d}:{m:02d}:{s:02d}]")
    print(f"   [유튜브 편집본]: \"{ys.text.strip()}\"")
    print(f"   [ChannelDNA 마커]: \"{vs.text.strip()}\"")
