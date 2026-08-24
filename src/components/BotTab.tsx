import React, { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  Bot,
  Key,
  ShieldCheck,
  Trash2,
  Copy,
  CheckCircle2,
  RefreshCw,
  Cloud,
  Info,
} from "lucide-react";

interface StreamerBinding {
  channel_id: string;
  streamer_name: string;
  target_dna_profile: string | null;
  passcode: string | null;
  master_discord_id: number | null;
  is_bound: number;
  last_processed_video_no: string | null;
  created_at: string | null;
  bound_at: string | null;
}

interface BotTabProps {
  streamers: string[];
  selectedStreamer: string;
  setSelectedStreamer: (name: string) => void;
  addLog: (msg: string, level?: string) => void;
}

export const BotTab: React.FC<BotTabProps> = ({
  streamers,
  selectedStreamer,
  setSelectedStreamer,
  addLog,
}) => {
  const [bindings, setBindings] = useState<StreamerBinding[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [channelUrl, setChannelUrl] = useState<string>("");
  const [targetDna, setTargetDna] = useState<string>("");
  const [issuedCard, setIssuedCard] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  const loadBindings = async () => {
    try {
      setIsLoading(true);
      const res = await invoke<StreamerBinding[]>("get_streamer_bindings");
      setBindings(res || []);
    } catch (e: any) {
      addLog(`바인딩 목록 조회 실패: ${e}`, "WARN");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadBindings();
  }, []);

  const handleSelectStreamer = async (name: string) => {
    setSelectedStreamer(name);
    if (!targetDna) setTargetDna(name);
    if (name) {
      try {
        const [solo] = await invoke<[any, any]>("get_two_track_profiles", { streamerName: name });
        if (solo && solo.chzzk_url) {
          setChannelUrl(solo.chzzk_url);
        }
      } catch {
        // ignore
      }
    }
  };

  const handleIssuePasscode = async () => {
    if (!selectedStreamer) {
      addLog("스트리머를 먼저 선택해 주세요.", "WARN");
      return;
    }
    const targetChannel = channelUrl.trim() || "b3e262a2795f17734c149afc738ad250";
    const selectedDna = targetDna || selectedStreamer;
    try {
      addLog(`[${selectedStreamer}] 1회용 등록 암호 발급 중 (적용 DNA: ${selectedDna})...`, "INFO");
      const passcode = await invoke<string>("issue_streamer_passcode", {
        streamerName: selectedStreamer,
        channelId: targetChannel,
        targetDnaProfile: selectedDna,
      });

      const copyText = `안녕하세요. 치지직 방송 종료 시 가편집 타임라인과 자막을 자동 전송하는 봇입니다.\n\n1. 봇 초대 링크를 통해 1:1 대화방을 엽니다.\n2. 대화창에 아래 명령어를 입력하여 등록을 완료해 주세요.\n👉 /인증 암호:${passcode}`;
      setIssuedCard(copyText);
      addLog(`✓ [${selectedStreamer}] 1회용 암호 발급 완료 (적용 DNA: ${selectedDna}): ${passcode}`, "SUCCESS");
      await loadBindings();
    } catch (e: any) {
      addLog(`암호 발급 오류: ${e}`, "ERROR");
    }
  };

  const handleUnbind = async (nameOrChannel: string) => {
    if (!confirm(`정말로 [${nameOrChannel}] 스트리머의 모니터링을 해지하시겠습니까?`)) return;
    try {
      const res = await invoke<boolean>("unbind_streamer", { streamerName: nameOrChannel });
      if (res) {
        addLog(`✓ [${nameOrChannel}] 모니터링 해지 완료`, "SUCCESS");
        await loadBindings();
      }
    } catch (e: any) {
      addLog(`해지 실패: ${e}`, "ERROR");
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    addLog("안내 문구가 클립보드에 복사되었습니다.", "INFO");
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Top Banner */}
      <div className="bg-[#121622] border border-[#1E2433] rounded-xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute right-0 top-0 w-80 h-80 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-3">
              <Bot className="w-6 h-6 text-[#00E5FF]" />
              디스코드 봇 & 24시간 클라우드 자동화 관제탑
            </h2>
            <p className="text-sm text-slate-400 mt-1">
              치지직 방송 종료를 2분 주기로 자동 감지하고, 관리자가 지정한 맞춤형 유튜브 DNA 그래프 유사도로 가편집 타임라인(Solo/Collab)을 추출하여 디스코드 DM으로 자동 직배송합니다.
            </p>
          </div>
          <button
            onClick={loadBindings}
            disabled={isLoading}
            className="flex items-center gap-2 px-3 py-2 bg-[#1A2030] hover:bg-[#232B40] text-slate-300 text-xs font-semibold rounded-lg transition-all border border-[#2B354C]"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-[#00E5FF]" : ""}`} />
            새로고침
          </button>
        </div>
      </div>

      {/* Grid: Issue Passcode & Cloud Architecture */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Issue Passcode (7 cols) */}
        <div className="lg:col-span-7 bg-[#121622] border border-[#1E2433] rounded-xl p-6 shadow-xl space-y-4">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Key className="w-4 h-4 text-[#00E5FF]" />
            1회용 스트리머 등록 암호 발급 & DNA 스타일 지정
          </h3>
          <p className="text-xs text-slate-400">
            스트리머를 선택하고 **적용할 DNA 편집 스타일**을 지정해 주세요. 본인 DNA뿐만 아니라 다른 유명 스트리머의 편집 DNA를 선택하여 적용할 수도 있습니다.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
            <div>
              <label className="text-xs font-semibold text-slate-400 block mb-1.5">
                1. 대상 스트리머
              </label>
              <select
                value={selectedStreamer}
                onChange={(e) => handleSelectStreamer(e.target.value)}
                className="w-full px-3 py-2 bg-[#0A0D14] border border-[#2B354C] rounded-lg text-sm text-white focus:outline-none focus:border-[#00E5FF]"
              >
                <option value="">스트리머 선택...</option>
                {streamers.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-400 block mb-1.5">
                2. 적용할 DNA 스타일
              </label>
              <select
                value={targetDna || selectedStreamer}
                onChange={(e) => setTargetDna(e.target.value)}
                className="w-full px-3 py-2 bg-[#0A0D14] border border-cyan-500/40 rounded-lg text-sm text-cyan-200 focus:outline-none focus:border-[#00E5FF]"
              >
                <option value="">(기본) 본인 스타일</option>
                {streamers.map((s) => (
                  <option key={s} value={s}>
                    {s} 스타일 DNA
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-400 block mb-1.5">
                3. 치지직 방송 주소 (주소창 복사)
              </label>
              <input
                type="text"
                value={channelUrl}
                onChange={(e) => setChannelUrl(e.target.value)}
                placeholder="https://chzzk.naver.com/스트리머_주소"
                className="w-full px-3 py-2 bg-[#0A0D14] border border-[#2B354C] rounded-lg text-sm text-white focus:outline-none focus:border-[#00E5FF]"
              />
            </div>
          </div>
          <p className="text-[11px] text-cyan-300/80 bg-cyan-950/20 px-3 py-1.5 rounded-lg border border-cyan-500/20">
            💡 인터넷 브라우저 주소창의 링크(예: https://chzzk.naver.com/b3e262a2...)를 그대로 복사/붙여넣기 하시면 32자리 고유 채널 ID가 100% 자동 인식됩니다.
          </p>

          <button
            onClick={handleIssuePasscode}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-sm font-bold rounded-lg shadow-lg transition-all"
          >
            <ShieldCheck className="w-4 h-4" />
            지정 DNA 연결 & 1회용 암호 발급
          </button>

          {/* Issued Card Area */}
          {issuedCard && (
            <div className="mt-4 p-4 bg-[#0A0D14] border border-cyan-500/30 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-[#00E5FF] flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4" />
                  스트리머 전달용 안내 문구 (클립보드 복사 가능)
                </span>
                <button
                  onClick={() => copyToClipboard(issuedCard)}
                  className="flex items-center gap-1.5 px-2.5 py-1 bg-cyan-500/20 hover:bg-cyan-500/30 text-[#00E5FF] text-xs font-bold rounded transition-all"
                >
                  <Copy className="w-3.5 h-3.5" />
                  {copied ? "복사완료!" : "문구 복사"}
                </button>
              </div>
              <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono bg-[#121622] p-3 rounded-lg border border-[#1E2433]">
                {issuedCard}
              </pre>
            </div>
          )}
        </div>

        {/* Right: Cloud Zero-Cost Architecture Card (5 cols) */}
        <div className="lg:col-span-5 bg-[#121622] border border-[#1E2433] rounded-xl p-6 shadow-xl space-y-4">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Cloud className="w-4 h-4 text-[#00E676]" />
            100% 무인 0원 클라우드 구조
          </h3>

          <div className="space-y-3 text-xs">
            <div className="p-3 bg-[#0A0D14] border border-[#1E2433] rounded-lg">
              <div className="flex items-center justify-between text-white font-bold mb-1">
                <span>1️⃣ 오라클 클라우드 (Always Free)</span>
                <span className="text-[#00E676] font-mono">평생 0원</span>
              </div>
              <p className="text-slate-400">
                디스코드 봇과 SQLite DB를 24시간 365일 상시 가동하며 치지직 API를 2분마다 감시합니다.
              </p>
            </div>

            <div className="p-3 bg-[#0A0D14] border border-[#1E2433] rounded-lg">
              <div className="flex items-center justify-between text-white font-bold mb-1">
                <span>2️⃣ Modal.com (L4 GPU 서버리스)</span>
                <span className="text-[#00E676] font-mono">월 $30 무료</span>
              </div>
              <p className="text-slate-400">
                방종 신호가 오면 지정된 DNA 그래프 곡선으로 2분 35초 만에 Solo/Collab 가편집과 자막을 동시 연산하고 즉시 소멸합니다.
              </p>
            </div>

            <div className="p-3 bg-cyan-950/20 border border-cyan-500/20 rounded-lg text-cyan-200">
              <p className="font-semibold flex items-center gap-1 mb-1">
                <Info className="w-3.5 h-3.5" />
                지정 DNA 매핑 자유도
              </p>
              <p className="text-[11px] text-cyan-300/80">
                신인 스트리머에게 침착맨이나 우왁굳 스타일의 DNA를 연결하여 그 스타일대로 가편집 XML을 뽑아낼 수 있습니다.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Table: 24/7 Monitored Streamers */}
      <div className="bg-[#121622] border border-[#1E2433] rounded-xl p-6 shadow-xl space-y-4">
        <h3 className="text-sm font-bold text-white flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-[#00E5FF]" />
          등록된 스트리머 모니터링 & 바인딩 현황 ({bindings.length}개)
        </h3>

        {bindings.length === 0 ? (
          <div className="text-center py-10 text-slate-500 text-sm">
            등록된 스트리머가 없습니다. 상단에서 스트리머를 선택하고 1회용 암호를 발급해 주세요.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-[#1E2433] text-slate-400 font-semibold bg-[#0A0D14]/60">
                  <th className="py-2.5 px-3">스트리머명</th>
                  <th className="py-2.5 px-3">적용 DNA 스타일</th>
                  <th className="py-2.5 px-3">치지직 채널 ID</th>
                  <th className="py-2.5 px-3">인증 상태</th>
                  <th className="py-2.5 px-3">수신자 디스코드 ID</th>
                  <th className="py-2.5 px-3">최근 처리 VOD</th>
                  <th className="py-2.5 px-3 text-right">관리</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2433]">
                {bindings.map((b) => (
                  <tr key={b.channel_id} className="hover:bg-[#1A2030]/50 transition-colors">
                    <td className="py-3 px-3 font-bold text-white">{b.streamer_name}</td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 font-mono text-[11px] border border-cyan-500/20">
                        {b.target_dna_profile || b.streamer_name}
                      </span>
                    </td>
                    <td className="py-3 px-3 font-mono text-slate-300 text-[11px]">{b.channel_id}</td>
                    <td className="py-3 px-3">
                      {b.is_bound === 1 ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-semibold text-[11px] border border-emerald-500/20">
                          ✓ 인증완료 (독점)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 font-semibold text-[11px] border border-amber-500/20">
                          ⏳ 대기중 (암호: {b.passcode})
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-3 font-mono text-slate-400">
                      {b.master_discord_id ? b.master_discord_id : "미지정"}
                    </td>
                    <td className="py-3 px-3 font-mono text-slate-400">
                      {b.last_processed_video_no ? b.last_processed_video_no : "없음"}
                    </td>
                    <td className="py-3 px-3 text-right">
                      <button
                        onClick={() => handleUnbind(b.streamer_name)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 font-semibold rounded transition-colors text-[11px] border border-rose-500/20"
                      >
                        <Trash2 className="w-3 h-3" />
                        해지
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
