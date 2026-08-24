use std::path::{Path, PathBuf};
use rusqlite::{params, Connection, Result};
use crate::models::{ChannelProfile, DbStats, VideoMetadata};

pub struct DbManager {
    db_path: PathBuf,
}

impl DbManager {
    pub fn new(db_path: Option<&Path>) -> Self {
        let path = if let Some(p) = db_path {
            p.to_path_buf()
        } else {
            PathBuf::from("channel_dna.db")
        };
        let manager = Self { db_path: path };
        manager.init_db().expect("Failed to initialize SQLite database");
        manager
    }

    fn get_conn(&self) -> Result<Connection> {
        let conn = Connection::open(&self.db_path)?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.pragma_update(None, "synchronous", "NORMAL")?;
        Ok(conn)
    }

    pub fn init_db(&self) -> Result<()> {
        let conn = self.get_conn()?;
        conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                title TEXT,
                duration REAL,
                avg_shot_length REAL,
                channel_name TEXT,
                file_path TEXT,
                video_type TEXT DEFAULT 'auto',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS segments (
                segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                start_time REAL,
                end_time REAL,
                duration REAL,
                rms_peak REAL,
                transcript TEXT,
                FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS channel_profiles (
                profile_id TEXT PRIMARY KEY,
                channel_name TEXT,
                sample_count INTEGER,
                avg_shot_length REAL,
                tension_interval REAL,
                silence_tolerance REAL,
                highlight_rms_threshold REAL,
                hook_duration REAL,
                custom_vocab TEXT,
                youtube_url TEXT,
                chzzk_url TEXT,
                profile_type TEXT DEFAULT 'general',
                burst_cut_asl REAL DEFAULT 2.5,
                burst_min_duration REAL DEFAULT 4.0,
                sub_voice_boost REAL DEFAULT 1.2,
                speech_ratio_mean REAL DEFAULT 0.65,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS marker_history (
                video_no TEXT PRIMARY KEY,
                file_path TEXT,
                json_data TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS issue_keywords (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                origin_context TEXT,
                source TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS streamer_bindings (
                channel_id TEXT PRIMARY KEY,
                streamer_name TEXT NOT NULL,
                passcode TEXT,
                master_discord_id INTEGER,
                is_bound INTEGER DEFAULT 0,
                last_processed_video_no TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                bound_at TEXT
            );
            "#,
        )?;
        Ok(())
    }

    pub fn get_db_stats(&self) -> Result<DbStats> {
        let conn = self.get_conn()?;
        let ch_count: i64 = conn.query_row(
            "SELECT COUNT(DISTINCT channel_name) FROM videos WHERE channel_name IS NOT NULL AND channel_name != ''",
            [],
            |r| r.get(0),
        ).unwrap_or(0);

        let v_count: i64 = conn.query_row("SELECT COUNT(*) FROM videos", [], |r| r.get(0)).unwrap_or(0);
        let p_count: i64 = conn.query_row("SELECT COUNT(*) FROM channel_profiles", [], |r| r.get(0)).unwrap_or(0);
        let m_count: i64 = conn.query_row("SELECT COUNT(*) FROM marker_history", [], |r| r.get(0)).unwrap_or(0);

        Ok(DbStats {
            channel_count: if ch_count > 0 { ch_count } else { 1 },
            video_count: v_count,
            profile_count: p_count,
            marker_count: m_count,
        })
    }

    pub fn get_all_videos(&self) -> Result<Vec<VideoMetadata>> {
        let conn = self.get_conn()?;
        let mut stmt = conn.prepare("SELECT video_id, title, duration, avg_shot_length, channel_name, file_path, video_type, created_at FROM videos ORDER BY created_at DESC")?;
        let rows = stmt.query_map([], |r| {
            Ok(VideoMetadata {
                video_id: r.get(0)?,
                title: r.get(1)?,
                duration: r.get(2)?,
                avg_shot_length: r.get(3)?,
                channel_name: r.get(4)?,
                file_path: r.get(5)?,
                video_type: r.get::<_, Option<String>>(6)?.unwrap_or_else(|| "auto".to_string()),
                created_at: r.get(7)?,
            })
        })?;

        let mut list = Vec::new();
        for r in rows {
            list.push(r?);
        }
        Ok(list)
    }

    #[allow(dead_code)]
    pub fn save_video(&self, v: &VideoMetadata) -> Result<()> {
        let conn = self.get_conn()?;
        let now = chrono::Local::now().to_rfc3339();
        conn.execute(
            r#"INSERT INTO videos (video_id, title, duration, avg_shot_length, channel_name, file_path, video_type, created_at)
               VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
               ON CONFLICT(video_id) DO UPDATE SET
                 title=excluded.title,
                 duration=excluded.duration,
                 avg_shot_length=excluded.avg_shot_length,
                 channel_name=excluded.channel_name,
                 video_type=excluded.video_type"#,
            params![v.video_id, v.title, v.duration, v.avg_shot_length, v.channel_name, v.file_path, v.video_type, now],
        )?;
        Ok(())
    }

    pub fn get_registered_streamers(&self) -> Result<Vec<String>> {
        let conn = self.get_conn()?;
        let mut stmt = conn.prepare("SELECT DISTINCT channel_name FROM channel_profiles WHERE channel_name IS NOT NULL AND channel_name != ''")?;
        let rows = stmt.query_map([], |r| r.get::<_, String>(0))?;
        
        let mut set = std::collections::BTreeSet::new();
        for name_res in rows {
            if let Ok(name) = name_res {
                let clean = name.replace("_Solo", "").replace("_Collab", "");
                if !clean.is_empty() && !clean.starts_with("🤖") {
                    set.insert(clean);
                }
            }
        }
        if set.is_empty() {
            set.insert("양망두".to_string());
        }
        Ok(set.into_iter().collect())
    }

    pub fn get_profile(&self, channel_name: &str) -> Result<Option<ChannelProfile>> {
        let conn = self.get_conn()?;
        let mut stmt = conn.prepare(
            r#"SELECT profile_id, channel_name, sample_count, avg_shot_length, tension_interval,
                      silence_tolerance, highlight_rms_threshold, hook_duration, custom_vocab,
                      youtube_url, chzzk_url, profile_type, burst_cut_asl, burst_min_duration,
                      sub_voice_boost, speech_ratio_mean, updated_at
               FROM channel_profiles WHERE channel_name = ?1 OR profile_id = ?1 LIMIT 1"#,
        )?;
        let mut rows = stmt.query_map(params![channel_name], |r| {
            Ok(ChannelProfile {
                profile_id: r.get(0)?,
                channel_name: r.get(1)?,
                sample_count: r.get(2)?,
                avg_shot_length: r.get(3)?,
                tension_interval: r.get(4)?,
                silence_tolerance: r.get(5)?,
                highlight_rms_threshold: r.get(6)?,
                hook_duration: r.get(7)?,
                custom_vocab: r.get(8)?,
                youtube_url: r.get(9)?,
                chzzk_url: r.get(10)?,
                profile_type: r.get::<_, Option<String>>(11)?.unwrap_or_else(|| "general".to_string()),
                burst_cut_asl: r.get(12)?,
                burst_min_duration: r.get(13)?,
                sub_voice_boost: r.get(14)?,
                speech_ratio_mean: r.get(15)?,
                updated_at: r.get(16)?,
            })
        })?;

        if let Some(res) = rows.next() {
            Ok(Some(res?))
        } else {
            Ok(None)
        }
    }

    pub fn save_profile(&self, p: &ChannelProfile) -> Result<()> {
        let conn = self.get_conn()?;
        let now = chrono::Local::now().to_rfc3339();
        conn.execute(
            r#"INSERT INTO channel_profiles (
                profile_id, channel_name, sample_count, avg_shot_length, tension_interval,
                silence_tolerance, highlight_rms_threshold, hook_duration, custom_vocab,
                youtube_url, chzzk_url, profile_type, burst_cut_asl, burst_min_duration,
                sub_voice_boost, speech_ratio_mean, updated_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17)
            ON CONFLICT(profile_id) DO UPDATE SET
                channel_name=excluded.channel_name,
                avg_shot_length=excluded.avg_shot_length,
                highlight_rms_threshold=excluded.highlight_rms_threshold,
                burst_cut_asl=excluded.burst_cut_asl,
                burst_min_duration=excluded.burst_min_duration,
                sub_voice_boost=excluded.sub_voice_boost,
                speech_ratio_mean=excluded.speech_ratio_mean,
                youtube_url=COALESCE(excluded.youtube_url, channel_profiles.youtube_url),
                chzzk_url=COALESCE(excluded.chzzk_url, channel_profiles.chzzk_url),
                updated_at=excluded.updated_at"#,
            params![
                p.profile_id, p.channel_name, p.sample_count, p.avg_shot_length,
                p.tension_interval, p.silence_tolerance, p.highlight_rms_threshold,
                p.hook_duration, p.custom_vocab, p.youtube_url, p.chzzk_url,
                p.profile_type, p.burst_cut_asl, p.burst_min_duration, p.sub_voice_boost,
                p.speech_ratio_mean, now
            ],
        )?;
        Ok(())
    }

    pub fn update_video_type(&self, video_id: &str, v_type: &str) -> Result<()> {
        let conn = self.get_conn()?;
        conn.execute("UPDATE videos SET video_type = ?1 WHERE video_id = ?2", params![v_type, video_id])?;
        Ok(())
    }

    #[allow(dead_code)]
    pub fn save_marker_history(&self, video_no: &str, file_path: &str, json_data: &str) -> Result<()> {
        let conn = self.get_conn()?;
        let now = chrono::Local::now().to_rfc3339();
        conn.execute(
            r#"INSERT INTO marker_history (video_no, file_path, json_data, created_at)
               VALUES (?1, ?2, ?3, ?4)
               ON CONFLICT(video_no) DO UPDATE SET file_path=excluded.file_path, json_data=excluded.json_data, created_at=excluded.created_at"#,
            params![video_no, file_path, json_data, now],
        )?;
        Ok(())
    }

    pub fn get_marker_history(&self, video_no: &str) -> Result<Option<(String, String)>> {
        let conn = self.get_conn()?;
        let mut stmt = conn.prepare("SELECT file_path, json_data FROM marker_history WHERE video_no = ?1 LIMIT 1")?;
        let mut rows = stmt.query(params![video_no])?;
        if let Some(row) = rows.next()? {
            Ok(Some((row.get(0)?, row.get(1)?)))
        } else {
            Ok(None)
        }
    }

    pub fn get_all_streamer_bindings(&self) -> Result<Vec<crate::models::StreamerBinding>> {
        let conn = self.get_conn()?;
        let mut stmt = conn.prepare(
            "SELECT channel_id, streamer_name, target_dna_profile, passcode, master_discord_id, is_bound, last_processed_video_no, created_at, bound_at
             FROM streamer_bindings ORDER BY created_at DESC"
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(crate::models::StreamerBinding {
                channel_id: row.get(0)?,
                streamer_name: row.get(1)?,
                target_dna_profile: row.get(2)?,
                passcode: row.get(3)?,
                master_discord_id: row.get(4)?,
                is_bound: row.get(5)?,
                last_processed_video_no: row.get(6)?,
                created_at: row.get(7)?,
                bound_at: row.get(8)?,
            })
        })?;

        let mut bindings = Vec::new();
        for r in rows {
            bindings.push(r?);
        }
        Ok(bindings)
    }

    pub fn create_passcode_binding(&self, channel_id: &str, streamer_name: &str, passcode: &str, target_dna_profile: &str) -> Result<()> {
        let conn = self.get_conn()?;
        let dna_prof = if target_dna_profile.trim().is_empty() { streamer_name } else { target_dna_profile.trim() };
        conn.execute(
            r#"INSERT INTO streamer_bindings (channel_id, streamer_name, target_dna_profile, passcode, is_bound)
               VALUES (?1, ?2, ?3, ?4, 0)
               ON CONFLICT(channel_id) DO UPDATE SET
                   streamer_name = excluded.streamer_name,
                   target_dna_profile = excluded.target_dna_profile,
                   passcode = excluded.passcode,
                   is_bound = 0,
                   master_discord_id = NULL,
                   bound_at = NULL"#,
            params![channel_id, streamer_name, dna_prof, passcode],
        )?;
        Ok(())
    }

    pub fn unbind_streamer(&self, channel_or_name: &str) -> Result<bool> {
        let conn = self.get_conn()?;
        let count = conn.execute(
            "DELETE FROM streamer_bindings WHERE channel_id = ?1 OR LOWER(streamer_name) = LOWER(?1)",
            params![channel_or_name],
        )?;
        Ok(count > 0)
    }
}

