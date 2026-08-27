import { useState, useEffect } from "react";
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
  const [profiles, setProfiles] = useState<ProfileItem[]>([]);

  // Global Console Logs & Progress Bar
  const [logs, setLogs] = useState<{ time: string; level: string; msg: string }[]>([]);
  const [progress] = useState<{ pct: number; msg: string }>({
    pct: 0,
    msg: "시스템 준비 완료",
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
      const resp = await fetch(`/api/profiles?t=${Date.now()}`, {
        headers: {
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache'
        }
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data.success && Array.isArray(data.profiles)) {
          setProfiles(data.profiles);
          addLog(`발화 프로필 ${data.profiles.length}개 로드 완료`, "INFO");
          return;
        }
      }
    } catch (e) {
      // fallback
    }
  };

  useEffect(() => {
    loadProfiles();
  }, []);

  return (
    <div className="flex flex-col min-h-screen bg-[#070a12] text-slate-100 font-sans antialiased select-none">
      {/* 1. Global Header */}
      <Header />

      {/* 2. Global Navigation Tabs */}
      <TabNav
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      {/* 3. Main Workspace Tab Panels */}
      <main className="flex-1 max-w-6xl w-full mx-auto p-4 sm:p-6 pb-20">
        {activeTab === "cut" && (
          <ScanTab
            profiles={profiles}
            addLog={addLog}
            onGoToProfiles={() => setActiveTab("profiles")}
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

      {/* 4. Real-time Status & Console Log Terminal Footer */}
      <TerminalFooter
        logs={logs}
        clearLogs={clearLogs}
        progress={progress}
      />
    </div>
  );
}
