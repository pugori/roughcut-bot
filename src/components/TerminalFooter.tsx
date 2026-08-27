import { useRef, useEffect } from "react";

interface TerminalFooterProps {
  logs: { time: string; level: string; msg: string }[];
  clearLogs: () => void;
  progress: { pct: number; msg: string };
}

export const TerminalFooter = ({ logs, clearLogs, progress }: TerminalFooterProps) => {
  const logEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <>
      {/* Global Progress Bar */}
      <div className="px-6 py-1.5 bg-[#0A0D14]">
        <div className="flex items-center justify-between text-[11px] mb-1">
          <span className="text-slate-400 font-medium">{progress.msg}</span>
          <span className="text-[#00E5FF] font-bold">{progress.pct}%</span>
        </div>
        <div className="w-full bg-[#161D2B] h-1.5 rounded-full overflow-hidden">
          <div className="bg-[#00E5FF] h-full transition-all duration-300" style={{ width: `${progress.pct}%` }}></div>
        </div>
      </div>

      {/* Terminal Log Console */}
      <footer className="h-32 bg-[#080A0F] border-t border-[#1E2638] flex flex-col px-6 py-2">
        <div className="flex items-center justify-between text-[11px] text-slate-400 pb-1 border-b border-[#1E2638]/50">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#00E676] animate-pulse"></span>
            <span className="font-bold text-slate-300">실시간 작업 상태</span>
          </div>
          <button onClick={clearLogs} className="hover:text-slate-200 text-[10px] cursor-pointer px-1.5 py-0.5 rounded hover:bg-slate-800 transition-colors">
            비우기
          </button>
        </div>
        <div className="flex-1 overflow-y-auto font-mono text-[10.5px] py-1 flex flex-col gap-0.5 scroll-smooth">
          {logs.map((l, i) => (
            <div key={i} className="flex gap-2 leading-relaxed">
              <span className="text-slate-600 shrink-0">[{l.time}]</span>
              <span
                className={
                  l.level === "SUCCESS"
                    ? "text-[#00E676] font-bold"
                    : l.level === "WARN"
                    ? "text-[#FFB74D]"
                    : l.level === "ERROR"
                    ? "text-[#FF5252] font-bold"
                    : "text-slate-300"
                }
              >
                [{l.level}] {l.msg}
              </span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      </footer>
    </>
  );
};
