import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Header } from "./components/Header";
import { TabNav } from "./components/TabNav";
import { ExtractTab } from "./components/ExtractTab";
import { ProfilesTab } from "./components/ProfilesTab";
import { ScanTab } from "./components/ScanTab";
import { BotTab } from "./components/BotTab";
import { TerminalFooter } from "./components/TerminalFooter";

interface DbStats {
  channel_count: number;
  video_count: number;
  profile_count: number;
  marker_count: number;
}

interface VideoMetadata {
  video_id: string;
  title: string;
  duration: number;
  avg_shot_length: number;
  channel_name: string | null;
  file_path: string | null;
  video_type: string;
  created_at: string | null;
}

interface ChannelProfile {
  profile_id: string;
  channel_name: string;
  sample_count: number;
  avg_shot_length: number;
  tension_interval: number;
  silence_tolerance: number;
  highlight_rms_threshold: number;
  hook_duration: number;
  custom_vocab?: string;
  youtube_url?: string;
  chzzk_url?: string;
  profile_type: string;
  burst_cut_asl?: number;
  burst_min_duration?: number;
  sub_voice_boost?: number;
  speech_ratio_mean?: number;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<"extract" | "profiles" | "scan" | "bot">("extract");
  const [stats, setStats] = useState<DbStats>({ channel_count: 0, video_count: 0, profile_count: 0, marker_count: 0 });
  const [streamers, setStreamers] = useState<string[]>([]);
  const [selectedStreamer, setSelectedStreamer] = useState<string>("");
  const [videos, setVideos] = useState<VideoMetadata[]>([]);
  const [soloProfile, setSoloProfile] = useState<ChannelProfile | null>(null);
  const [collabProfile, setCollabProfile] = useState<ChannelProfile | null>(null);

  // Global Console Logs & Progress Bar
  const [logs, setLogs] = useState<{ time: string; level: string; msg: string }[]>([]);
  const [progress, setProgress] = useState<{ pct: number; msg: string }>({ pct: 0, msg: "시스템 준비 완료 (Ready)" });

  const addLog = (msg: string, level: string = "INFO") => {
    const time = new Date().toTimeString().split(" ")[0];
    setLogs((prev) => [...prev.slice(-250), { time, level, msg }]);
  };

  const loadInitialData = async () => {
    try {
      const s: DbStats = await invoke("get_system_stats");
      setStats(s);
      const stList: string[] = await invoke("get_registered_streamers");
      setStreamers(stList);
      const vList: VideoMetadata[] = await invoke("get_video_catalog");
      setVideos(vList);
      addLog("ChannelDNA Pro Rust Core 엔진 및 SQLite DB 연동 완료 (Standalone Native Mode)", "SUCCESS");
    } catch (e) {
      addLog(`시스템 초기화 경고: ${e}`, "WARN");
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (selectedStreamer) {
      invoke<[ChannelProfile | null, ChannelProfile | null]>("get_two_track_profiles", { streamerName: selectedStreamer })
        .then(([solo, collab]) => {
          setSoloProfile(solo);
          setCollabProfile(collab);
          addLog(`프로필 로드 완료: '${selectedStreamer}' (솔로 ASL: ${solo?.avg_shot_length.toFixed(2) || "5.08"}s / 합방 ASL: ${collab?.avg_shot_length.toFixed(2) || "7.54"}s)`);
        })
        .catch((e) => addLog(`프로필 로드 오류: ${e}`, "ERROR"));
    }
  }, [selectedStreamer]);

  const handleToggleVideoType = async (videoId: string) => {
    try {
      const [title, newType]: [string, string] = await invoke("toggle_video_type", { videoId });
      addLog(`영상 '${title.slice(0, 20)}...' 분류를 [${newType.toUpperCase()}]로 전환 및 DB 재계산 완료!`, "SUCCESS");
      const vList: VideoMetadata[] = await invoke("get_video_catalog");
      setVideos(vList);
      if (selectedStreamer) {
        const [solo, collab]: [ChannelProfile | null, ChannelProfile | null] = await invoke("get_two_track_profiles", { streamerName: selectedStreamer });
        setSoloProfile(solo);
        setCollabProfile(collab);
      }
    } catch (e) {
      addLog(`분류 전환 실패: ${e}`, "ERROR");
    }
  };

  const handleRecalculateDna = async () => {
    if (!selectedStreamer) return;
    try {
      const [solo, collab]: [ChannelProfile, ChannelProfile] = await invoke("recalculate_dna", { streamerName: selectedStreamer });
      setSoloProfile(solo);
      setCollabProfile(collab);
      addLog(`'${selectedStreamer}' 솔로(ASL: ${solo.avg_shot_length.toFixed(2)}s) & 합방(ASL: ${collab.avg_shot_length.toFixed(2)}s) DNA 재계산 완료!`, "SUCCESS");
    } catch (e) {
      addLog(`DNA 재계산 오류: ${e}`, "ERROR");
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0A0D14] text-slate-200 select-none overflow-hidden font-sans">
      <Header channelCount={stats.channel_count} videoCount={stats.video_count} />
      <TabNav activeTab={activeTab} setActiveTab={setActiveTab} />

      <main className="flex-1 px-6 py-2 overflow-hidden bg-[#0A0D14]">
        <div className="h-full bg-[#121622] border border-[#1E2638] rounded-b-xl rounded-tr-xl p-4 overflow-y-auto flex flex-col gap-3">
          {activeTab === "extract" && (
            <ExtractTab
              streamers={streamers}
              videos={videos}
              onRefresh={loadInitialData}
              onToggleVideoType={handleToggleVideoType}
              addLog={addLog}
              setProgress={setProgress}
            />
          )}

          {activeTab === "profiles" && (
            <ProfilesTab
              streamers={streamers}
              selectedStreamer={selectedStreamer}
              setSelectedStreamer={setSelectedStreamer}
              soloProfile={soloProfile}
              collabProfile={collabProfile}
              onRecalculateDna={handleRecalculateDna}
              onRefresh={loadInitialData}
              addLog={addLog}
            />
          )}

          {activeTab === "scan" && (
            <ScanTab
              streamers={streamers}
              addLog={addLog}
              setProgress={setProgress}
            />
          )}

          {activeTab === "bot" && (
            <BotTab
              streamers={streamers}
              selectedStreamer={selectedStreamer}
              setSelectedStreamer={setSelectedStreamer}
              addLog={addLog}
            />
          )}
        </div>
      </main>

      <TerminalFooter logs={logs} clearLogs={() => setLogs([])} progress={progress} />
    </div>
  );
}
