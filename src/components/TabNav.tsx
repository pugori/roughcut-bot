import { Video, Sliders, Bot } from "lucide-react";

interface TabNavProps {
  activeTab: "extract" | "profiles" | "bot";
  setActiveTab: (tab: "extract" | "profiles" | "bot") => void;
}

export const TabNav = ({ activeTab, setActiveTab }: TabNavProps) => (
  <nav className="flex items-center gap-2 px-6 pt-2 bg-[#0A0D14]">
    <button
      onClick={() => setActiveTab("extract")}
      className={`flex items-center gap-2 px-5 py-2.5 text-xs font-bold rounded-t-lg transition-all ${
        activeTab === "extract"
          ? "bg-[#121622] text-[#00E5FF] border-t-2 border-[#00E5FF] shadow-lg"
          : "text-slate-400 hover:text-slate-200 hover:bg-[#121622]/50"
      }`}
    >
      <Video className="w-4 h-4" />
      1. 📥 유튜브 채널 일괄 수집 & DNA 학습
    </button>
    <button
      onClick={() => setActiveTab("profiles")}
      className={`flex items-center gap-2 px-5 py-2.5 text-xs font-bold rounded-t-lg transition-all ${
        activeTab === "profiles"
          ? "bg-[#121622] text-[#00E5FF] border-t-2 border-[#00E5FF] shadow-lg"
          : "text-slate-400 hover:text-slate-200 hover:bg-[#121622]/50"
      }`}
    >
      <Sliders className="w-4 h-4" />
      2. 📊 스트리머 투트랙 DNA 프로필 뷰어
    </button>
    <button
      onClick={() => setActiveTab("bot")}
      className={`flex items-center gap-2 px-5 py-2.5 text-xs font-bold rounded-t-lg transition-all ${
        activeTab === "bot"
          ? "bg-[#121622] text-[#00E5FF] border-t-2 border-[#00E5FF] shadow-lg"
          : "text-slate-400 hover:text-slate-200 hover:bg-[#121622]/50"
      }`}
    >
      <Bot className="w-4 h-4" />
      3. 🤖 디스코드 봇 & 24h 클라우드 관리
    </button>
  </nav>
);
