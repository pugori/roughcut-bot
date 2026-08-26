import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Header } from "./components/Header";
import { TabNav } from "./components/TabNav";
import { ScanTab } from "./components/ScanTab";
import { ProfilesTab } from "./components/ProfilesTab";
import { TerminalFooter } from "./components/TerminalFooter";

interface ProfileItem {
  profile_id: string;
  profile_name: string;
  chzzk_channel_url?: string;
  solo_profile?: any;
  collab_profile?: any;
  created_at?: string;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<"cut" | "profiles">("cut");
  const [profiles, setProfiles] = useState<ProfileItem[]>([
    {
      profile_id: "prof_default_01",
      profile_name: "하이텐션 게임 방송 스타일",
      solo_profile: { avg_shot_length: 3.8, silence_tolerance: 0.8, highlight_rms_threshold: 0.95 },
      collab_profile: { avg_shot_length: 2.2, silence_tolerance: 1.2, highlight_rms_threshold: 1.10 },
    },
    {
      profile_id: "prof_default_02",
      profile_name: "잔잔한 토크/소통 방송 스타일",
      solo_profile: { avg_shot_length: 4.2, silence_tolerance: 0.9, highlight_rms_threshold: 0.90 },
      collab_profile: { avg_shot_length: 2.6, silence_tolerance: 1.3, highlight_rms_threshold: 1.05 },
    },
  ]);

  // Global Console Logs & Progress Bar
  const [logs, setLogs] = useState<{ time: string; level: string; msg: string }[]>([]);
  const [progress] = useState<{ pct: number; msg: string }>({
    pct: 0,
    msg: "시스템 준비 완료 (100% Local Offline Sandbox)",
  });

  const addLog = (msg: string, level: string = "INFO") => {
    const time = new Date().toTimeString().split(" ")[0];
    setLogs((prev) => [...prev.slice(-250), { time, level, msg }]);
  };

  const clearLogs = () => {
    setLogs([]);
  };

  const loadProfiles = async () => {
    try {
      const pList: ProfileItem[] = await invoke("get_user_profiles_list");
      if (pList && pList.length > 0) {
        setProfiles(pList);
      }
      addLog(`발화 프로필 ${pList?.length || 2}개 로드 완료`, "INFO");
    } catch (e) {
      // Fallback
    }
  };

  useEffect(() => {
    addLog("ChannelDNA Studio v2.0 로컬 엔진 초기화 완료 (100% Local Mode)", "SUCCESS");
    loadProfiles();
  }, []);

  return (
    <div className="min-h-screen bg-[#0a0d14] text-[#f8fafc] flex flex-col font-sans select-none">
      {/* Top Header */}
      <Header channelCount={profiles.length} videoCount={1} />

      {/* 2-Tab Navigation Bar */}
      <TabNav activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Main Content Area */}
      <main className="flex-1 max-w-6xl w-full mx-auto p-6">
        {activeTab === "cut" && (
          <ScanTab
            profiles={profiles}
            addLog={addLog}
            onNavigateToProfiles={() => setActiveTab("profiles")}
          />
        )}

        {activeTab === "profiles" && (
          <ProfilesTab
            profiles={profiles}
            onRefreshProfiles={loadProfiles}
            addLog={addLog}
          />
        )}
      </main>

      {/* Bottom Terminal Log Footer */}
      <TerminalFooter logs={logs} clearLogs={clearLogs} progress={progress} />
    </div>
  );
}
