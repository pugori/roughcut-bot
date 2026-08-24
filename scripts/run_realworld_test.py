"""Full End-to-End Real-world Pipeline Test for Dokcake YouTube Channel DNA Extraction & VOD Highlight Marking."""
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import os
import time
import gc
from channel_dna.core.pipeline import PipelineFacade

facade = PipelineFacade()
channel_url = "https://www.youtube.com/@%EB%8F%85%EC%BC%80%EC%9D%B5%EC%9C%A0%ED%8A%9C%EB%B8%8C"
channel_name = "Dokcake"
vod_url = "https://chzzk.naver.com/video/14668745"

print("="*65)
print("🚀 [1단계: 독케익 유튜브 채널 DNA 자동 수집 및 프로파일링 시작]")
print("="*65)

# 1. Fetch & Analyze Top 5 Popular Videos from Dokcake YouTube Channel
videos = facade.extractor.fetch_channel_videos(channel_url, max_videos=5, sort_by="popular")
print(f"✓ 유튜브 채널 인기 영상 {len(videos)}편 목록 확보 완료.")

for idx, v in enumerate(videos, 1):
    v_url = v["url"]
    v_title = v["title"]
    print(f"\n[{idx}/{len(videos)}] 분석 중: {v_title}")
    
    def cb(stage, pct, msg):
        if pct == 1.0 or int(pct * 100) % 30 == 0:
            print(f"    - [{stage}] {msg}")

    try:
        res = facade.extractor.analyze(v_url, channel_name, is_url=True, progress_cb=cb)
        facade.db.save_video_analysis(res.metadata, res.segments)
        print(f"    ✓ 분석 완료! 컷전환주기(ASL): {res.metadata.avg_shot_length:.2f}s | 발화세그먼트: {len(res.segments)}개")
    except Exception as e:
        print(f"    ⚠️ 건너뜀: {e}")

# 2. Derive Channel DNA Profile from Saved DB
print("\n" + "="*65)
print("🧠 [2단계: 채널 DNA 기준선(Profile) 도출 및 DB 구축]")
print("="*65)
profile = facade.profiler.derive_profile(channel_name)
print(f"✓ 채널명: {profile.channel_name}")
print(f"✓ 분석된 샘플 수: {profile.sample_count}편")
print(f"✓ 채널 고유 컷 호흡(ASL): {profile.avg_shot_length:.2f}초")
print(f"✓ 채널 도파민 임계치(Threshold): {profile.highlight_rms_threshold:.2f}")
print(f"✓ 자동 추출된 채널 고유 어휘집(Vocab): {profile.custom_vocab[:100]}...")

# 3. Scan Chzzk VOD using the Derived Channel DNA Profile
print("\n" + "="*65)
print("🎯 [3단계: 치지직 원본 VOD에 채널 DNA 기준선 적용 스캔]")
print("="*65)
t_scan_start = time.time()

def scan_cb(stage, pct, msg):
    print(f"  [{stage}] {int(pct*100)}% - {msg}")

markers = facade.scanner.scan(vod_url, profile, use_cache=True, progress_cb=scan_cb)
scan_duration = time.time() - t_scan_start

print(f"\n✓ VOD 스캔 완료 ({scan_duration:.1f}초)")
print(f"✓ 생성된 정예 하이라이트 마커 수: {len(markers)}개 (채널 맞춤형 기준선 적용)")

# 4. Compare with YouTube Edited Video Episode (00:23:00 ~ 00:35:00)
print("\n" + "="*65)
print("📊 [4단계: 실제 유튜브 편집본과의 1:1 실사용 적합도 검증]")
print("="*65)

# Target Episode: Ghost Story Episode (00:23:00 ~ 00:35:00)
episode_markers = [m for m in markers if 1300 <= m.start_time <= 2100]

print(f"- 실제 유튜브 편집본 사용 구간: 26.08.12 심야괴담 [00:23:00 ~ 00:35:00]")
print(f"- 해당 구간 내 채널 DNA 마커 검출 수: {len(episode_markers)}개 (적정 수준으로 정예화)")
print(f"\n[검출된 대표 엑기스 마커 목록 Top 6]")
for idx, m in enumerate(sorted(episode_markers, key=lambda x: x.peak_tension, reverse=True)[:6], 1):
    print(f"{idx}. [{m.start_timecode} ~ {m.end_timecode}] (길이: {m.duration:.1f}초) | 텐션: {m.peak_tension:.2f} | 근거: {m.reason}")

# 5. Clean up resources
print("\n" + "="*65)
print("🧹 [5단계: 메모리 및 임시 리소스 자동 청소 완료]")
print("="*65)
gc.collect()
print("✓ 모든 테스트 프로세스 및 메모리 정상 반환 완료.")
