"""Comprehensive Verification Script on Real 2.5-hour MP4 VOD File."""
import sys
import os
import re
from pathlib import Path

# Ensure root dir in sys.path
sys.path.insert(0, "c:/dna")

from channel_dna.core.pipeline import PipelineFacade
from channel_dna.core.models import ChannelProfile


def verify_real_vod_package():
    real_video_path = r"C:\Users\cha85\Downloads\de1aeec2-9a3f-11f1-88a6-a0369ffbd890.mp4"
    if not os.path.exists(real_video_path):
        print(f"[ERROR] Video file not found: {real_video_path}")
        return False

    print("=================================================================")
    print("      Real VOD File NLE Markers & Subtitles Verification         ")
    print("=================================================================")
    print(f"Target VOD: {real_video_path}")

    facade = PipelineFacade()
    
    # 1. Get or create test channel profile
    profile = facade.db.get_profile("Dokcake")
    if not profile:
        profile = ChannelProfile(
            profile_id="Dokcake",
            channel_name="Dokcake",
            sample_count=5,
            avg_shot_length=3.5,
            tension_interval=45.0,
            silence_tolerance=0.8,
            highlight_rms_threshold=1.5,
            hook_duration=15.0,
            custom_vocab="독케익,다이브,억까,클러치,개추"
        )
        facade.db.save_profile(profile)

    print("\n[Step 1] Scanning Real VOD for Highlights & Tension Peaks...")
    def progress_cb(stage, pct, msg):
        safe_msg = msg.encode("ascii", "replace").decode("ascii")
        print(f"  [{stage}] ({int(pct*100)}%) {safe_msg}")

    # Scan VOD audio
    markers = facade.scanner.scan(
        vod_path=real_video_path,
        profile=profile,
        use_cache=True,
        progress_cb=progress_cb
    )

    print(f"\n[OK] Detected {len(markers)} highlight markers across the VOD timeline.")
    if not markers:
        print("[FAIL] No markers detected.")
        return False

    # Print top 5 markers with timecodes
    print("\n[Sample Highlight Markers Detected]:")
    for i, m in enumerate(markers[:5], 1):
        print(f"  Marker {i}: {m.start_timecode} --> {m.end_timecode} (Dur: {m.duration:.1f}s, Peak: {m.peak_tension:.2f}x)")

    # 2. Extract Subtitles for the highlight markers
    print("\n[Step 2] Generating Subtitles for Markers using faster-whisper C++ Engine...")
    audio_data = facade.audio_engine.extract_audio_in_memory(real_video_path)
    
    # Select first 3 markers across timeline to test STT speed and timestamp accuracy
    test_markers = markers[:3]
    subtitles = facade.subtitle_engine.generate_subtitles_for_markers(
        audio_data=audio_data,
        markers=test_markers,
        custom_vocab_prompt=profile.custom_vocab,
        progress_cb=progress_cb
    )

    print(f"\n[OK] Generated {len(subtitles)} subtitle lines for test highlight markers.")

    # 3. Export Package (XML, EDL, SRT)
    print("\n[Step 3] Exporting 3-File Multi-NLE Package (XML, EDL, SRT)...")
    out_dir = r"c:\dna\output\real_vod_test"
    pkg = facade.export_streamer_package(
        vod_title="Real_VOD_Test",
        vod_date="2026-08-21",
        markers=test_markers,
        subtitles=subtitles,
        output_dir=out_dir,
        fps=60.0
    )

    print(f"Output Package Folder: {pkg['folder']}")
    print(f"  - Premiere XML: {pkg['premiere_xml']}")
    print(f"  - DaVinci EDL : {pkg['davinci_edl']}")
    print(f"  - Subtitles SRT: {pkg['subtitles_srt']}")
    
    # Check CSV is NOT in pkg or folder
    folder = Path(pkg['folder'])
    csv_files = list(folder.glob("*.csv"))
    assert len(csv_files) == 0, f"CSV file should NOT be created! Found: {csv_files}"
    print("[OK] Confirmed: NO CSV file was created in the package.")

    # 4. Verify Subtitle Absolute Timestamps
    print("\n[Step 4] Verifying Subtitle Absolute Timestamp Alignment...")
    srt_path = Path(pkg['subtitles_srt'])
    with open(srt_path, "r", encoding="utf-8") as f:
        srt_content = f.read()

    print("\n--- [Generated SRT Content Sample] ---")
    safe_srt_sample = srt_content[:1500].encode("ascii", "replace").decode("ascii")
    print(safe_srt_sample)
    print("--------------------------------------")

    # Parse SRT blocks and verify times
    timecode_pattern = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")
    matches = timecode_pattern.findall(srt_content)
    
    assert len(matches) > 0, "No valid SRT timecodes found in subtitle file!"
    
    print("\n[SRT Timecode Range Check]:")
    for idx, tc in enumerate(matches, 1):
        s_h, s_m, s_s, s_ms, e_h, e_m, e_s, e_ms = [int(x) for x in tc]
        start_sec = s_h * 3600 + s_m * 60 + s_s + s_ms / 1000.0
        end_sec = e_h * 3600 + e_m * 60 + e_s + e_ms / 1000.0
        
        # Find corresponding marker
        matching_m = next((m for m in test_markers if (m.start_time - 3.0) <= start_sec <= (m.end_time + 5.0)), None)
        assert matching_m is not None, f"Subtitle {idx} ({start_sec}s) does not match any highlight marker timeline! (Was at 0s?)"
        print(f"  Line {idx}: {start_sec:07.2f}s ~ {end_sec:07.2f}s -> Aligned with Marker [{matching_m.start_timecode} ~ {matching_m.end_timecode}] [OK]")

    print("\n=================================================================")
    print("[SUCCESS] All Real VOD NLE & Absolute Subtitle Tests PASSED!")
    print("=================================================================")
    return True

if __name__ == "__main__":
    success = verify_real_vod_package()
    sys.exit(0 if success else 1)
