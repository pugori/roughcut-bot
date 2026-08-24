use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VideoMetadata {
    pub video_id: String,
    pub title: String,
    pub duration: f64,
    pub avg_shot_length: f64,
    pub channel_name: Option<String>,
    pub file_path: Option<String>,
    pub video_type: String, // "auto", "solo", "collab"
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChannelProfile {
    pub profile_id: String,
    pub channel_name: String,
    pub sample_count: i32,
    pub avg_shot_length: f64,
    pub tension_interval: f64,
    pub silence_tolerance: f64,
    pub highlight_rms_threshold: f64,
    pub hook_duration: f64,
    pub custom_vocab: Option<String>,
    pub youtube_url: Option<String>,
    pub chzzk_url: Option<String>,
    pub profile_type: String, // "solo", "collab", "general"
    pub burst_cut_asl: Option<f64>,
    pub burst_min_duration: Option<f64>,
    pub sub_voice_boost: Option<f64>,
    pub speech_ratio_mean: Option<f64>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[allow(dead_code)]
pub struct ScanMarker {
    pub start_time: f64,
    pub end_time: f64,
    pub duration: f64,
    pub peak_tension: f64,
    pub label: String,
    pub reason: String,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[allow(dead_code)]
pub struct SubtitleItem {
    pub index: i32,
    pub start_time: f64,
    pub end_time: f64,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DbStats {
    pub channel_count: i64,
    pub video_count: i64,
    pub profile_count: i64,
    pub marker_count: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChzzkVideoItem {
    pub video_no: String,
    pub title: String,
    #[serde(default)]
    pub date_str: String,
    #[serde(default)]
    pub duration_str: String,
    #[serde(default)]
    pub duration_sec: f64,
    #[serde(default)]
    pub vod_url: String,
    #[serde(default)]
    pub channel_name: String,
    #[serde(default)]
    pub publish_date: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamerBinding {
    pub channel_id: String,
    pub streamer_name: String,
    pub target_dna_profile: Option<String>,
    pub passcode: Option<String>,
    pub master_discord_id: Option<i64>,
    pub is_bound: i32,
    pub last_processed_video_no: Option<String>,
    pub created_at: Option<String>,
    pub bound_at: Option<String>,
}
