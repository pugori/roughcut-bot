import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { DownloadCloud, ExternalLink } from "lucide-react";

interface VideoMetadata {
  video_id: string;
  title: string;
  duration: number;
  avg_shot_length: number;
  channel_name: string | null;
  video_type: string;
}

interface ExtractTabProps {
  streamers: string[];
  videos: VideoMetadata[];
  onRefresh: () => void;
  onToggleVideoType: (videoId: string) => void;
  addLog: (msg: string, level?: string) => void;
  setProgress: (val: { pct: number; msg: string }) => void;
}

export const ExtractTab = ({
  streamers,
  videos,
  onRefresh,
  onToggleVideoType,
  addLog,
  setProgress,
}: ExtractTabProps) => {
  const [streamerNameInput, setStreamerNameInput] = useState(streamers[0] || "양망두");
  const [youtubeUrlInput, setYoutubeUrlInput] = useState("https://www.youtube.com/@양망두");
  const [batchCountOption, setBatchCountOption] = useState("최신/인기 20편");
  const [sortOption, setSortOption] = useState("밸런스 (인기+최신 균등)");
  const [isCollecting, setIsCollecting] = useState(false);

  const handleStartExtract = async () => {
    const sName = streamerNameInput || (streamers.length > 0 ? streamers[0] : "양망두");
    const countNum = parseInt(batchCountOption.replace(/[^0-9]/g, "")) || 20;

    setIsCollecting(true);
    setProgress({ pct: 25, msg: "유튜브 채널 메타데이터 파싱 및 비디오 로드 중..." });
    addLog(`[채널 일괄 수집 시작] 채널: '${sName}' | 대상: ${youtubeUrlInput} | 기준: ${sortOption} 상위 ${countNum}편`, "INFO");

    let ticker: any = null;
    try {
      let currentPct = 25;
      const stages = [
        "유튜브 인기/최신 대표 영상 다운로드 중...",
        "PySceneDetect 프레임별 컷 전환(ASL) 고속 검출 중...",
        "1k~3.5k 보컬 텐션 분포 및 음화 구간 산출 중...",
        "스트리머 솔로/합방 2-Track Baseline DB 적재 중...",
      ];
      let stageIdx = 0;
      ticker = setInterval(() => {
        currentPct = Math.min(96, currentPct + Math.floor(Math.random() * 5) + 2);
        stageIdx = (stageIdx + 1) % stages.length;
        setProgress({ pct: currentPct, msg: stages[stageIdx] + " (" + currentPct + "%)" });
      }, 3000);

      addLog(`[ChannelScan] 유튜브 채널 인기/최신 영상 동시 다운로드 및 1k~3.5k 오디오 텐션 분석 중...`, "INFO");

      const updatedVideos: VideoMetadata[] = await invoke("start_channel_batch_collection", {
        streamerName: sName,
        channelUrl: youtubeUrlInput,
        count: countNum,
        sortBy: sortOption,
      });

      if (ticker) clearInterval(ticker);
      setProgress({ pct: 100, msg: "채널 일괄 수집 및 DNA 학습 완료" });
      addLog(`🎉 [채널 일괄 수집 완료] '${sName}' 대표 영상 총 ${updatedVideos.length}편 SQLite DB 적재 완료!`, "SUCCESS");
      onRefresh();

      // Auto Cloud Sync for newly extracted DNA
      try {
        const [solo, collab] = await invoke<[any, any]>("get_two_track_profiles", { streamerName: sName });
        const CLOUD_BOT_URL = "https://roughcut-bot.onrender.com";
        const ADMIN_SECRET = "channeldna-secret-admin-key-2026";
        if (solo) {
          await fetch(`${CLOUD_BOT_URL}/api/sync_profile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ secret_key: ADMIN_SECRET, profile: solo }),
          });
        }
        if (collab) {
          await fetch(`${CLOUD_BOT_URL}/api/sync_profile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ secret_key: ADMIN_SECRET, profile: collab }),
          });
        }
        addLog(`☁️ '${sName}' DNA 프로필이 24시간 클라우드 봇으로 자동 업로드되었습니다! (로컬 PC를 종료해도 정상 가동)`, "SUCCESS");
      } catch (cloudErr) {
        addLog(`클라우드 자동 업로드 알림: ${cloudErr}`, "INFO");
      }
    } catch (e) {
      if (ticker) clearInterval(ticker);
      addLog(`수집 실패: ${e}`, "ERROR");
      setProgress({ pct: 0, msg: "수집 오류" });
    } finally {
      setIsCollecting(false);
    }
  };

  const handleOpenVideoLink = (_title: string, videoId: string) => {
    const targetUrl = videoId.startsWith("http") ? videoId : `https://www.youtube.com/watch?v=${videoId}`;
    addLog(`🌐 유튜브 영상 바로 열기: ${targetUrl}`, "INFO");
    invoke("open_external_url", { url: targetUrl }).catch((err) => addLog(`브라우저 열기 오류: ${err}`, "ERROR"));
  };

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="border-b border-[#1E2638] pb-2">
        <h2 className="text-sm font-bold text-[#00E5FF] flex items-center gap-2">
          <DownloadCloud className="w-4 h-4" /> 📥 1. 유튜브 채널 일괄 수집 & DNA 학습 (Channel DNA Extractor)
        </h2>
        <p className="text-[11px] text-slate-400 mt-0.5">
          • 채널의 대표 편집 영상을 수집/분석하여 평균 컷 길이(ASL), 음화 구간, 1k~3.5k 텐션 분포를 학습합니다.
          <br />• 하단 '배치 수집'을 진행하면 채널의 고유 편집 스타일(솔로/합방) Baseline이 DB에 영구 구축됩니다.
        </p>
      </div>

      {/* Inputs Card */}
      <div className="bg-[#0E121B] border border-[#1E2638] rounded-lg p-3.5 flex flex-col gap-2.5 text-xs shadow-md">
        {/* Row 1 */}
        <div className="grid grid-cols-12 gap-2 items-center">
          <span className="col-span-2 font-bold text-slate-300">👤 스트리머명:</span>
          <input
            type="text"
            placeholder="스트리머명 입력 (예: 양망두)"
            value={streamerNameInput}
            onChange={(e) => {
              setStreamerNameInput(e.target.value);
              setYoutubeUrlInput(`https://www.youtube.com/@${e.target.value}`);
            }}
            className="col-span-5 bg-[#161C2A] border border-[#1E2638] rounded px-3 py-1.5 text-slate-200 focus:outline-none focus:border-[#00E5FF]"
          />
          <select
            value={streamerNameInput}
            onChange={(e) => {
              setStreamerNameInput(e.target.value);
              setYoutubeUrlInput(`https://www.youtube.com/@${e.target.value}`);
            }}
            className="col-span-5 bg-[#161C2A] border border-[#1E2638] rounded px-3 py-1.5 text-slate-200 focus:outline-none"
          >
            {streamers.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        {/* Row 2 */}
        <div className="grid grid-cols-12 gap-2 items-center">
          <span className="col-span-2 font-bold text-slate-300">📺 유튜브 채널 주소:</span>
          <input
            type="text"
            value={youtubeUrlInput}
            onChange={(e) => setYoutubeUrlInput(e.target.value)}
            className="col-span-5 bg-[#161C2A] border border-[#1E2638] rounded px-3 py-1.5 text-slate-200 focus:outline-none focus:border-[#00E5FF]"
          />
          <select
            value={sortOption}
            onChange={(e) => setSortOption(e.target.value)}
            className="col-span-3 bg-[#161C2A] border border-[#1E2638] rounded px-3 py-1.5 text-slate-200 focus:outline-none"
          >
            <option>밸런스 (인기+최신 균등)</option>
            <option>인기순 상위</option>
            <option>최신순 상위</option>
          </select>
          <select
            value={batchCountOption}
            onChange={(e) => setBatchCountOption(e.target.value)}
            className="col-span-2 bg-[#161C2A] border border-[#1E2638] rounded px-3 py-1.5 text-slate-200 focus:outline-none"
          >
            <option>최신/인기 5편</option>
            <option>최신/인기 10편</option>
            <option>최신/인기 20편</option>
          </select>
        </div>

        {/* Action Button */}
        <button
          disabled={isCollecting}
          onClick={handleStartExtract}
          className="mt-1 w-full py-2.5 rounded-lg bg-[#00897B] hover:bg-[#00796B] active:scale-[0.99] text-white font-bold flex items-center justify-center gap-2 shadow-lg transition-all cursor-pointer disabled:opacity-50"
        >
          <DownloadCloud className="w-4 h-4" />
          {isCollecting ? "채널 영상 고속 수집 및 컷 분석 중..." : "🚀 채널 자동 일괄 수집 & DNA 학습 (추천)"}
        </button>
      </div>

      {/* Videos List Table */}
      <div className="flex-1 border border-[#1E2638] rounded-lg overflow-hidden bg-[#0E121B] flex flex-col">
        <div className="flex items-center justify-between px-3 py-2 border-b border-[#1E2638] bg-[#121622]">
          <span className="text-xs font-bold text-slate-300">
            📑 로컬 DB 누적 분석 영상 목록 (Accumulated DB Videos: {videos.length}편)
          </span>
          <button
            onClick={onRefresh}
            className="text-[11px] text-[#00E5FF] hover:underline flex items-center gap-1 cursor-pointer"
          >
            🔄 새로고침
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#161C2A] text-slate-400 border-b border-[#1E2638] sticky top-0">
                <th className="py-2 px-3 w-10 text-center">#</th>
                <th className="py-2 px-3 w-24 text-center">유형 (클릭전환)</th>
                <th className="py-2 px-3 w-28">스트리머</th>
                <th className="py-2 px-3 w-40">재생시간 / ASL</th>
                <th className="py-2 px-3">영상 제목 (클릭 시 브라우저 열기)</th>
              </tr>
            </thead>
            <tbody>
              {videos.map((v, i) => (
                <tr key={v.video_id} className="border-b border-[#1E2638]/40 hover:bg-[#182030] transition-colors">
                  <td className="py-1.5 px-3 text-center font-bold text-slate-500">{i + 1}</td>
                  <td className="py-1.5 px-3 text-center">
                    <button
                      onClick={() => onToggleVideoType(v.video_id)}
                      className={`px-2 py-0.5 rounded text-[10px] font-bold transition-transform active:scale-95 cursor-pointer ${
                        v.video_type === "collab"
                          ? "bg-[#4A148C] text-[#E1BEE7] hover:bg-[#6A1B9A] border border-[#AB47BC]/30"
                          : "bg-[#01579B] text-[#B3E5FC] hover:bg-[#0288D1] border border-[#00E5FF]/30"
                      }`}
                    >
                      {v.video_type === "collab" ? "👥 합방" : "👤 솔로"}
                    </button>
                  </td>
                  <td className="py-1.5 px-3 font-bold text-[#00E5FF]">[{v.channel_name || "Unknown"}]</td>
                  <td className="py-1.5 px-3 text-slate-400 font-mono">
                    ⏱ {Math.floor(v.duration / 60)}분{Math.floor(v.duration % 60)}초 | ASL {v.avg_shot_length.toFixed(2)}s
                  </td>
                  <td className="py-1.5 px-3 text-slate-200 truncate max-w-md font-medium">
                    <button
                      onClick={() => handleOpenVideoLink(v.title, v.video_id)}
                      className="hover:text-[#00E5FF] hover:underline flex items-center gap-1.5 cursor-pointer text-left w-full text-xs font-semibold"
                    >
                      <ExternalLink className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="truncate">{v.title}</span>
                    </button>
                  </td>
                </tr>
              ))}
              {videos.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-12 text-center text-slate-500">
                    수집된 분석 영상이 없습니다. 상단에서 [배치 수집]을 시작해 보세요.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

