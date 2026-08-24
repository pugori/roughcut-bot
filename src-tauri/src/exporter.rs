#![allow(dead_code)]
use std::fs::File;
use std::io::Write;
use std::path::Path;
use crate::models::{ScanMarker, SubtitleItem};

pub struct Exporter;

impl Exporter {
    pub fn export_premiere_xml(markers: &[ScanMarker], output_path: &Path, sequence_name: &str) -> std::io::Result<()> {
        let mut file = File::create(output_path)?;
        writeln!(file, r#"<?xml version="1.0" encoding="UTF-8"?>"#)?;
        writeln!(file, r#"<!DOCTYPE xmeml>"#)?;
        writeln!(file, r#"<xmeml version="4">"#)?;
        writeln!(file, r#"  <sequence>"#)?;
        writeln!(file, r#"    <name>{}</name>"#, sequence_name)?;
        writeln!(file, r#"    <rate><timebase>30</timebase><ntsc>TRUE</ntsc></rate>"#)?;
        writeln!(file, r#"    <media><video><track>"#)?;

        for (idx, m) in markers.iter().enumerate() {
            let in_frame = (m.start_time * 30.0) as i64;
            let out_frame = (m.end_time * 30.0) as i64;
            writeln!(file, r#"      <clipitem id="clipitem-{}">"#, idx + 1)?;
            writeln!(file, r#"        <name>{}</name>"#, m.label)?;
            writeln!(file, r#"        <in>{}</in>"#, in_frame)?;
            writeln!(file, r#"        <out>{}</out>"#, out_frame)?;
            writeln!(file, r#"      </clipitem>"#)?;
        }

        writeln!(file, r#"    </track></video></media>"#)?;
        writeln!(file, r#"  </sequence>"#)?;
        writeln!(file, r#"</xmeml>"#)?;
        Ok(())
    }

    pub fn export_edl(markers: &[ScanMarker], output_path: &Path, sequence_name: &str) -> std::io::Result<()> {
        let mut file = File::create(output_path)?;
        writeln!(file, "TITLE: {}", sequence_name)?;
        writeln!(file, "FCM: NON-DROP FRAME\n")?;

        for (idx, m) in markers.iter().enumerate() {
            let start_tc = Self::to_timecode(m.start_time);
            let end_tc = Self::to_timecode(m.end_time);
            writeln!(file, "{:03}  AX       V     C        {} {} {} {}", idx + 1, start_tc, end_tc, start_tc, end_tc)?;
            writeln!(file, "* FROM CLIP NAME: {}", m.label)?;
            writeln!(file, "* COMMENT: {}\n", m.reason)?;
        }
        Ok(())
    }

    pub fn export_srt(subtitles: &[SubtitleItem], output_path: &Path) -> std::io::Result<()> {
        let mut file = File::create(output_path)?;
        for s in subtitles {
            let start_tc = Self::to_srt_time(s.start_time);
            let end_tc = Self::to_srt_time(s.end_time);
            writeln!(file, "{}", s.index)?;
            writeln!(file, "{} --> {}", start_tc, end_tc)?;
            writeln!(file, "{}\n", s.text)?;
        }
        Ok(())
    }

    fn to_timecode(seconds: f64) -> String {
        let total_sec = seconds as i64;
        let h = total_sec / 3600;
        let m = (total_sec % 3600) / 60;
        let s = total_sec % 60;
        let frames = ((seconds.fract()) * 30.0) as i64;
        format!("{:02}:{:02}:{:02}:{:02}", h, m, s, frames)
    }

    fn to_srt_time(seconds: f64) -> String {
        let total_sec = seconds as i64;
        let h = total_sec / 3600;
        let m = (total_sec % 3600) / 60;
        let s = total_sec % 60;
        let ms = ((seconds.fract()) * 1000.0) as i64;
        format!("{:02}:{:02}:{:02},{:03}", h, m, s, ms)
    }
}

