import { Scissors, UserCheck } from "lucide-react";

interface TabNavProps {
  activeTab: "cut" | "profiles";
  setActiveTab: (tab: "cut" | "profiles") => void;
}

export const TabNav = ({ activeTab, setActiveTab }: TabNavProps) => (
  <nav className="flex items-center gap-2 px-6 pt-2 bg-[#0A0D14] border-b border-[#212c3f]">
    <button
      onClick={() => setActiveTab("cut")}
      className={`flex items-center gap-2 px-6 py-3 text-sm font-bold rounded-t-lg transition-all ${
        activeTab === "cut"
          ? "bg-[#111726] text-[#38bdf8] border-t-2 border-[#0284c7] shadow-lg"
          : "text-slate-400 hover:text-slate-200 hover:bg-[#111726]/50"
      }`}
    >
      <Scissors className="w-4 h-4 text-[#38bdf8]" />
      🎬 VOD 자동 가편집
    </button>
    <button
      onClick={() => setActiveTab("profiles")}
      className={`flex items-center gap-2 px-6 py-3 text-sm font-bold rounded-t-lg transition-all ${
        activeTab === "profiles"
          ? "bg-[#111726] text-[#38bdf8] border-t-2 border-[#0284c7] shadow-lg"
          : "text-slate-400 hover:text-slate-200 hover:bg-[#111726]/50"
      }`}
    >
      <UserCheck className="w-4 h-4 text-[#38bdf8]" />
      👤 발화 프로필 관리 (3+3 등록)
    </button>
  </nav>
);
