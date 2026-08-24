"""Extract actual tension DNA from YouTube edit and update the Channel Profile."""
import sys
sys.path.insert(0, r"c:\dna")
import numpy as np
from pathlib import Path
from scipy.signal import find_peaks

from channel_dna.core.audio_engine import AudioEngine
from channel_dna.core.db import DBManager
from channel_dna.core.models import ChannelProfile

# Paths
YOUTUBE_EDIT_PATH = str(Path.home() / "Downloads" / "YouTube_Dokcake_Edit_Psychopath.mp4")
CHANNEL_NAME = "Dokcake"

print("=" * 70)
print(f"  EXTRACTING CHANNEL DNA (Motif Template) FOR: {CHANNEL_NAME}")
print("=" * 70)

engine = AudioEngine()
db = DBManager()

# 1. Ensure profile exists
profile = db.get_profile(CHANNEL_NAME)
if not profile:
    print(f"  Profile '{CHANNEL_NAME}' not found in DB. Creating default...")
    from channel_dna.core.graph_engine import GraphEngine
    profile = ChannelProfile(
        profile_id=CHANNEL_NAME, channel_name=CHANNEL_NAME,
        avg_shot_length=3.5, tension_interval=45.0, silence_tolerance=0.8,
        highlight_rms_threshold=0.95, hook_duration=15.0, sample_count=1,
        motif_template=GraphEngine().get_default_motif_template()
    )
    db.save_profile(profile)

# 2. Extract Audio from YouTube Edit
print(f"  Loading YouTube edit audio: {Path(YOUTUBE_EDIT_PATH).name}...")
audio_data = engine.extract_audio_in_memory(YOUTUBE_EDIT_PATH)

# 3. Compute Multiband Tension
print("  Computing multiband tension curve for the edit...")
times, tension = engine.compute_sliding_tension(audio_data)

# 4. Extract Real Motif Shapes (Peaks)
print("  Extracting morphological shapes from peaks...")
# Find distinct peaks in the edit (prominent highlights)
peaks, properties = find_peaks(tension, height=1.5, distance=int(10.0 / 0.25))

# We need a 32-point template representing roughly 8 seconds (0.25s hop * 32 = 8s)
# Let's extract 12 points before peak and 20 points after peak (build-up -> burst -> decay)
MOTIF_SIZE = 32
PRE_PEAK = 12
POST_PEAK = 20

extracted_shapes = []

for p in peaks:
    if p - PRE_PEAK >= 0 and p + POST_PEAK < len(tension):
        shape = tension[p - PRE_PEAK : p + POST_PEAK].copy()
        
        # Normalize shape (min-max to 0-1 range)
        s_min = np.min(shape)
        s_max = np.max(shape)
        if s_max - s_min > 1e-6:
            shape_norm = (shape - s_min) / (s_max - s_min)
            extracted_shapes.append(shape_norm)

if extracted_shapes:
    print(f"  Averaging {len(extracted_shapes)} real highlight shapes...")
    # Average them to find the true channel DNA
    avg_shape = np.mean(extracted_shapes, axis=0)
    
    # Apply slight smoothing
    from scipy.ndimage import gaussian_filter1d
    avg_shape = gaussian_filter1d(avg_shape, sigma=1.0)
    
    # Re-normalize
    avg_shape = (avg_shape - np.min(avg_shape)) / (np.max(avg_shape) - np.min(avg_shape))
    
    # Update profile
    old_template = profile.motif_template
    profile.motif_template = [round(float(x), 4) for x in avg_shape]
    db.save_profile(profile)
    
    print("\n  [MOTIF TEMPLATE UPDATED SUCCESSFULLY]")
    print(f"  Old Template (Default Gaussian):")
    print("  " + ", ".join([f"{x:.2f}" for x in old_template[:10]]) + " ...")
    print(f"  New Template (Real DNA):")
    print("  " + ", ".join([f"{x:.2f}" for x in profile.motif_template[:10]]) + " ...")
    
    # Calculate optimal buffer_after_sec from the decay curve
    # Find how many points it takes to drop below 30% of peak energy
    post_peak_curve = avg_shape[PRE_PEAK:]
    decay_points = 0
    for val in post_peak_curve:
        decay_points += 1
        if val < 0.3:
            break
    
    decay_sec = decay_points * 0.25
    print(f"\n  Analyzed Decay (여운): {decay_sec:.1f} seconds")
    print("  -> Marker post-padding should be adjusted accordingly.")
    
else:
    print("  Failed to extract meaningful peaks from the edit.")

print("=" * 70)
