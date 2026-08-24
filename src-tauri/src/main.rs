// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod db;
mod exporter;
mod models;
mod service;

use std::sync::Arc;
use tokio::sync::Mutex;
use tauri::State;
use crate::models::{ChannelProfile, ChzzkVideoItem, DbStats, VideoMetadata};
use crate::service::ServiceState;

struct AppState(Arc<Mutex<ServiceState>>);

#[tauri::command]
async fn get_system_stats(state: State<'_, AppState>) -> Result<DbStats, String> {
    let svc = state.0.lock().await;
    svc.get_system_stats()
}

#[tauri::command]
async fn get_registered_streamers(state: State<'_, AppState>) -> Result<Vec<String>, String> {
    let svc = state.0.lock().await;
    svc.get_registered_streamers()
}

#[tauri::command]
async fn get_video_catalog(state: State<'_, AppState>) -> Result<Vec<VideoMetadata>, String> {
    let svc = state.0.lock().await;
    svc.get_video_catalog()
}

#[tauri::command]
async fn get_two_track_profiles(state: State<'_, AppState>, streamer_name: String) -> Result<(Option<ChannelProfile>, Option<ChannelProfile>), String> {
    let svc = state.0.lock().await;
    svc.get_two_track_profiles(&streamer_name)
}

#[tauri::command]
async fn recalculate_dna(state: State<'_, AppState>, streamer_name: String) -> Result<(ChannelProfile, ChannelProfile), String> {
    let svc = state.0.lock().await;
    svc.recalculate_dna(&streamer_name)
}

#[tauri::command]
async fn start_channel_batch_collection(
    state: State<'_, AppState>,
    streamer_name: String,
    channel_url: String,
    count: usize,
    sort_by: String,
) -> Result<Vec<VideoMetadata>, String> {
    let svc_arc = state.0.clone();
    tokio::task::spawn_blocking(move || {
        let svc = svc_arc.blocking_lock();
        svc.start_channel_batch_collection(&streamer_name, &channel_url, count, &sort_by)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn fetch_chzzk_vod_catalog(
    state: State<'_, AppState>,
    channel_target: String,
) -> Result<Vec<ChzzkVideoItem>, String> {
    let svc_arc = state.0.clone();
    tokio::task::spawn_blocking(move || {
        let svc = svc_arc.blocking_lock();
        svc.fetch_chzzk_vod_catalog(&channel_target)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn start_vod_timeline_scan(
    state: State<'_, AppState>,
    vod_url_or_no: String,
    streamer_name: String,
    dna_profile_name: String,
) -> Result<String, String> {
    let svc_arc = state.0.clone();
    tokio::task::spawn_blocking(move || {
        let svc = svc_arc.blocking_lock();
        svc.start_vod_timeline_scan(&vod_url_or_no, &streamer_name, &dna_profile_name)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn toggle_video_type(state: State<'_, AppState>, video_id: String) -> Result<(String, String), String> {
    let svc = state.0.lock().await;
    svc.toggle_video_type(&video_id)
}

#[tauri::command]
async fn check_vod_status(state: State<'_, AppState>, channel_name: String, video_no: String, date_str: String, title: String) -> Result<(String, String, String, String), String> {
    let svc = state.0.lock().await;
    Ok(svc.check_vod_status(&channel_name, &video_no, &date_str, &title))
}

#[tauri::command]
fn open_external_url(url: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        std::process::Command::new("rundll32")
            .args(["url.dll,FileProtocolHandler", &url])
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
async fn select_video_file() -> Result<Option<String>, String> {
    tokio::task::spawn_blocking(|| {
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x08000000;
            let ps_script = r#"
            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            Add-Type -AssemblyName System.Windows.Forms
            $f = New-Object System.Windows.Forms.OpenFileDialog
            $f.Filter = "영상 파일 (*.mp4;*.ts;*.mkv;*.mov;*.avi)|*.mp4;*.ts;*.mkv;*.mov;*.avi|모든 파일 (*.*)|*.*"
            $f.Title = "분석할 로컬 영상 파일을 선택하세요"
            if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                [Console]::Out.WriteLine($f.FileName)
            }
            "#;
            let output = std::process::Command::new("powershell")
                .args(["-NoProfile", "-NonInteractive", "-Command", ps_script])
                .creation_flags(CREATE_NO_WINDOW)
                .output()
                .map_err(|e| e.to_string())?;

            let stdout_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if stdout_str.is_empty() {
                Ok(None)
            } else {
                Ok(Some(stdout_str))
            }
        }
        #[cfg(not(target_os = "windows"))]
        {
            Ok(None)
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn open_folder(folder_path: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        
        let raw_path = folder_path.trim();
        let target_path = if raw_path.is_empty() {
            std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from(".")).join("markers")
        } else {
            let mut p = std::path::PathBuf::from(raw_path);
            if p.is_relative() {
                p = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from(".")).join(p);
            }
            p
        };

        if !target_path.exists() {
            let _ = std::fs::create_dir_all(&target_path);
        }

        let full_str = target_path.to_string_lossy().to_string();
        
        // Spawn explorer via cmd /c start "" "path" to ensure it opens reliably in all Windows environments
        std::process::Command::new("cmd")
            .args(["/C", "start", "", &full_str])
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
async fn get_streamer_bindings(state: State<'_, AppState>) -> Result<Vec<crate::models::StreamerBinding>, String> {
    let svc = state.0.lock().await;
    svc.get_streamer_bindings()
}

#[tauri::command]
async fn issue_streamer_passcode(
    state: State<'_, AppState>,
    streamer_name: String,
    channel_id: String,
    target_dna_profile: String,
) -> Result<String, String> {
    let svc = state.0.lock().await;
    svc.issue_streamer_passcode(&streamer_name, &channel_id, &target_dna_profile)
}

#[tauri::command]
async fn unbind_streamer(state: State<'_, AppState>, streamer_name: String) -> Result<bool, String> {
    let svc = state.0.lock().await;
    svc.unbind_streamer(&streamer_name)
}

fn main() {
    tauri::Builder::default()
        .manage(AppState(Arc::new(Mutex::new(ServiceState::new()))))
        .invoke_handler(tauri::generate_handler![
            get_system_stats,
            get_registered_streamers,
            get_video_catalog,
            get_two_track_profiles,
            recalculate_dna,
            start_channel_batch_collection,
            fetch_chzzk_vod_catalog,
            start_vod_timeline_scan,
            toggle_video_type,
            check_vod_status,
            open_external_url,
            open_folder,
            select_video_file,
            get_streamer_bindings,
            issue_streamer_passcode,
            unbind_streamer,
        ])
        .run(tauri::generate_context!())
        .expect("error while running ChannelDNA Pro Tauri application");
}




