use std::path::PathBuf;
use crate::db::DbManager;
use crate::models::{ChannelProfile, ChzzkVideoItem, DbStats, VideoMetadata};

pub struct ServiceState {
    pub db: DbManager,
}

impl ServiceState {
    pub fn new() -> Self {
        Self {
            db: DbManager::new(None),
        }
    }

    pub fn get_system_stats(&self) -> Result<DbStats, String> {
        self.db.get_db_stats().map_err(|e| e.to_string())
    }

    pub fn get_registered_streamers(&self) -> Result<Vec<String>, String> {
        self.db.get_registered_streamers().map_err(|e| e.to_string())
    }

    pub fn get_video_catalog(&self) -> Result<Vec<VideoMetadata>, String> {
        self.db.get_all_videos().map_err(|e| e.to_string())
    }

    pub fn get_two_track_profiles(&self, streamer_name: &str) -> Result<(Option<ChannelProfile>, Option<ChannelProfile>), String> {
        let p_solo = self.db.get_profile(&format!("{}_Solo", streamer_name)).unwrap_or(None);
        let p_collab = self.db.get_profile(&format!("{}_Collab", streamer_name)).unwrap_or(None);
        Ok((p_solo, p_collab))
    }

    pub fn recalculate_dna(&self, streamer_name: &str) -> Result<(ChannelProfile, ChannelProfile), String> {
        let videos = self.db.get_all_videos().map_err(|e| e.to_string())?;
        let filtered: Vec<&VideoMetadata> = videos.iter().filter(|v| {
            v.channel_name.as_deref().unwrap_or("").contains(streamer_name)
        }).collect();

        let mut solo_asls = Vec::new();
        let mut collab_asls = Vec::new();

        for v in filtered {
            if v.video_type == "collab" {
                collab_asls.push(v.avg_shot_length);
            } else {
                solo_asls.push(v.avg_shot_length);
            }
        }

        let solo_asl = if !solo_asls.is_empty() {
            solo_asls.iter().sum::<f64>() / solo_asls.len() as f64
        } else {
            4.80
        };

        let collab_asl = if !collab_asls.is_empty() {
            collab_asls.iter().sum::<f64>() / collab_asls.len() as f64
        } else {
            6.77
        };

        let existing_solo = self.db.get_profile(&format!("{}_Solo", streamer_name)).unwrap_or(None);
        let existing_collab = self.db.get_profile(&format!("{}_Collab", streamer_name)).unwrap_or(None);

        let yt_url = existing_solo.as_ref().and_then(|p| p.youtube_url.clone())
            .or_else(|| existing_collab.as_ref().and_then(|p| p.youtube_url.clone()))
            .unwrap_or_else(|| format!("https://www.youtube.com/@{}", streamer_name));

        let ch_url = existing_solo.as_ref().and_then(|p| p.chzzk_url.clone())
            .or_else(|| existing_collab.as_ref().and_then(|p| p.chzzk_url.clone()))
            .unwrap_or_default();

        let solo_p = ChannelProfile {
            profile_id: format!("{}_Solo", streamer_name),
            channel_name: format!("{}_Solo", streamer_name),
            sample_count: solo_asls.len() as i32,
            avg_shot_length: solo_asl,
            tension_interval: 45.0,
            silence_tolerance: 0.8,
            highlight_rms_threshold: 0.95,
            hook_duration: 15.0,
            custom_vocab: Some(format!("{}, 방송, 하이라이트", streamer_name)),
            youtube_url: Some(yt_url.clone()),
            chzzk_url: if ch_url.is_empty() { None } else { Some(ch_url.clone()) },
            profile_type: "solo".to_string(),
            burst_cut_asl: Some(2.5),
            burst_min_duration: Some(4.0),
            sub_voice_boost: Some(1.2),
            speech_ratio_mean: Some(0.65),
            updated_at: None,
        };

        let collab_p = ChannelProfile {
            profile_id: format!("{}_Collab", streamer_name),
            channel_name: format!("{}_Collab", streamer_name),
            sample_count: collab_asls.len() as i32,
            avg_shot_length: collab_asl,
            tension_interval: 45.0,
            silence_tolerance: 1.2,
            highlight_rms_threshold: 1.10,
            hook_duration: 15.0,
            custom_vocab: Some(format!("{}, 합방, 게임", streamer_name)),
            youtube_url: Some(yt_url),
            chzzk_url: if ch_url.is_empty() { None } else { Some(ch_url) },
            profile_type: "collab".to_string(),
            burst_cut_asl: Some(3.2),
            burst_min_duration: Some(4.5),
            sub_voice_boost: Some(1.5),
            speech_ratio_mean: Some(0.70),
            updated_at: None,
        };

        self.db.save_profile(&solo_p).map_err(|e| e.to_string())?;
        self.db.save_profile(&collab_p).map_err(|e| e.to_string())?;

        Ok((solo_p, collab_p))
    }

    pub fn start_channel_batch_collection(
        &self,
        streamer_name: &str,
        channel_url: &str,
        count: usize,
        sort_by: &str,
    ) -> Result<Vec<VideoMetadata>, String> {
        let count_str = count.to_string();
        let target_url = if channel_url.is_empty() {
            format!("https://www.youtube.com/@{}", streamer_name)
        } else {
            channel_url.to_string()
        };

        // Real Open-Source Python Worker (yt-dlp, PySceneDetect, FFmpeg, Librosa)
        let mut cmd = std::process::Command::new("python");
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000);
        }
        cmd.env("PYTHONIOENCODING", "utf-8")
           .env("PYTHONUTF8", "1");
        let _ = cmd
            .args([
                "-m",
                "channel_dna.worker",
                "batch_extract",
                "--url",
                &target_url,
                "--streamer",
                streamer_name,
                "--count",
                &count_str,
                "--sort",
                sort_by,
            ])
            .output();

        let _ = self.recalculate_dna(streamer_name);
        self.db.get_all_videos().map_err(|e| e.to_string())
    }

    pub fn fetch_chzzk_vod_catalog(&self, channel_target: &str) -> Result<Vec<ChzzkVideoItem>, String> {
        let mut cmd = std::process::Command::new("python");
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000);
        }
        cmd.env("PYTHONIOENCODING", "utf-8")
           .env("PYTHONUTF8", "1");
        let output = cmd
            .args([
                "-m",
                "channel_dna.worker",
                "fetch_chzzk",
                "--target",
                channel_target,
            ])
            .output()
            .map_err(|e| e.to_string())?;

        let stdout_str = String::from_utf8_lossy(&output.stdout);
        for line in stdout_str.lines() {
            if let Ok(val) = serde_json::from_str::<serde_json::Value>(line) {
                if val.get("type").and_then(|t| t.as_str()) == Some("chzzk_vods") {
                    if let Some(vods) = val.get("vods") {
                        if let Ok(items) = serde_json::from_value::<Vec<ChzzkVideoItem>>(vods.clone()) {
                            return Ok(items);
                        }
                    }
                }
            }
        }
        Ok(Vec::new())
    }

    pub fn start_vod_timeline_scan(
        &self,
        vod_url_or_no: &str,
        streamer_name: &str,
        dna_profile_name: &str,
    ) -> Result<String, String> {
        let mut cmd = std::process::Command::new("python");
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000);
        }
        cmd.env("PYTHONIOENCODING", "utf-8")
           .env("PYTHONUTF8", "1");
        let output = cmd
            .args([
                "-m",
                "channel_dna.worker",
                "scan_vod",
                "--vod",
                vod_url_or_no,
                "--streamer",
                streamer_name,
                "--dna",
                dna_profile_name,
            ])
            .output()
            .map_err(|e| e.to_string())?;

        let stdout_str = String::from_utf8_lossy(&output.stdout);
        Ok(stdout_str.to_string())
    }

    pub fn toggle_video_type(&self, video_id: &str) -> Result<(String, String), String> {
        let videos = self.db.get_all_videos().map_err(|e| e.to_string())?;
        let v = videos.into_iter().find(|item| item.video_id == video_id).ok_or_else(|| "Video not found".to_string())?;
        let new_type = if v.video_type == "collab" { "solo" } else { "collab" };
        self.db.update_video_type(video_id, new_type).map_err(|e| e.to_string())?;
        
        if let Some(ch) = v.channel_name {
            let _ = self.recalculate_dna(&ch);
        }
        Ok((v.title, new_type.to_string()))
    }

    pub fn check_vod_status(&self, channel_name: &str, video_no: &str, date_str: &str, _title: &str) -> (String, String, String, String) {
        let sanitized_date = date_str.replace("-", "").replace(".", "");
        let ch_marker_dir = PathBuf::from("markers").join(channel_name);
        
        let mut matched_folder: Option<PathBuf> = None;
        if ch_marker_dir.exists() {
            if let Ok(entries) = std::fs::read_dir(&ch_marker_dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.is_dir() {
                        let name = path.file_name().unwrap_or_default().to_string_lossy();
                        if (!sanitized_date.is_empty() && name.starts_with(&sanitized_date)) || name.contains(video_no) {
                            if path.read_dir().map(|mut d| d.next().is_some()).unwrap_or(false) {
                                matched_folder = Some(path);
                                break;
                            }
                        }
                    }
                }
            }
        }

        if let Some(folder) = matched_folder {
            let folder_str = folder.to_string_lossy().to_string();
            ("✅ 분석완료 (패키지)".to_string(), "#00E676".to_string(), "#0B291A".to_string(), folder_str)
        } else if let Ok(Some((_, _))) = self.db.get_marker_history(video_no) {
            ("⚠️ 분석이력 (파일없음)".to_string(), "#FFB74D".to_string(), "#33220E".to_string(), "".to_string())
        } else {
            ("⚪ 미분석".to_string(), "#94A3B8".to_string(), "#1E2433".to_string(), "".to_string())
        }
    }

    pub fn get_streamer_bindings(&self) -> Result<Vec<crate::models::StreamerBinding>, String> {
        self.db.get_all_streamer_bindings().map_err(|e| e.to_string())
    }

    pub fn issue_streamer_passcode(&self, streamer_name: &str, channel_id: &str, target_dna_profile: &str) -> Result<String, String> {
        let clean_prefix: String = streamer_name.chars().filter(|c| c.is_alphanumeric()).take(4).collect();
        let prefix = if clean_prefix.is_empty() { "CDNA".to_string() } else { clean_prefix };
        let nanos = chrono::Local::now().timestamp_subsec_nanos();
        let rand_num = (nanos % 9000) + 1000;
        let passcode = format!("{}-{}", prefix, rand_num);

        // Automatically extract clean 32-char ID from full browser URL if pasted
        let clean_channel_id = if let Ok(re) = regex::Regex::new(r"([a-f0-9]{32})") {
            if let Some(caps) = re.captures(channel_id) {
                caps.get(1).map(|m| m.as_str().to_string()).unwrap_or_else(|| channel_id.trim().to_string())
            } else {
                channel_id.trim().to_string()
            }
        } else {
            channel_id.trim().to_string()
        };

        self.db.create_passcode_binding(&clean_channel_id, streamer_name, &passcode, target_dna_profile)
            .map_err(|e| e.to_string())?;

        Ok(passcode)
    }

    pub fn unbind_streamer(&self, channel_or_name: &str) -> Result<bool, String> {
        self.db.unbind_streamer(channel_or_name).map_err(|e| e.to_string())
    }
}



