import { Activity } from "lucide-react";

interface HeaderProps {
  channelCount: number;
  videoCount: number;
}

export const Header = ({ channelCount, videoCount }: HeaderProps) => (
  <header className="flex items-center justify-between px-6 py-2.5 bg-[#10141E] border-b border-[#1E2638]">
    <div className="flex items-center gap-3">
      <span className="text-2xl">🧬</span>
      <span className="text-lg font-bold text-[#00E5FF] tracking-wide">ChannelDNA Pro</span>
      <span className="text-[11px] px-2.5 py-0.5 rounded bg-[#0D2738] text-[#00E5FF] font-bold border border-[#00E5FF]/30">
        v2.5 Production Studio
      </span>
      <span className="text-xs text-slate-400 ml-2">| AI 멀티모달 채널 학습 & 60fps 초고속 컷 편집 어시스턴트</span>
    </div>
    <div className="flex items-center gap-3 text-xs">
      <div className="flex items-center gap-2 px-3 py-1 rounded bg-[#0C261B] text-[#00E676] border border-[#00E676]/30 font-semibold">
        <span className="w-2 h-2 rounded-full bg-[#00E676] animate-pulse"></span>
        SQLite DB 연동 ({channelCount}개 채널 / {videoCount}편)
      </div>
      <div className="flex items-center gap-1.5 px-3 py-1 rounded bg-[#182030] text-slate-300 border border-slate-700 font-semibold">
        <Activity className="w-3.5 h-3.5 text-[#00E5FF]" />
        Rust Core Engine
      </div>
    </div>
  </header>
);
