import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { PlayCircle, Zap, FolderOpen, AlertTriangle, FileVideo, Radio, Upload, ExternalLink } from "lucide-react";

interface ChzzkVideoItem {
  video_no: string;
  title: string;
  duration_str: string;
  date_str: string;
  vod_url: string;
}

interface VODRow {
  video_no: string;
  title: string;
  date_str: string;
  duration_str: string;
  status_text: string;
  status_fg: string;
  status_bg: string;
  folder_path: string;
  vod_url?: string;
}

interface ScanTabProps {
  streamers: string[];
  addLog: (msg: string, level?: string) => void;
  setProgress: (val: { pct: number; msg: string }) => void;
}

export const ScanTab = ({ streamers, addLog, setProgress }: ScanTabProps) => {
  const [sourceMode, setSourceMode] = useState<"chzzk" | "local">("chzzk");
  const [scanStreamerPreset, setScanStreamerPreset] = useState(streamers[0] || "양망두");
  const [selectedDnaStyle, setSelectedDnaStyle] = useState(streamers[0] ? `${streamers[0]}_Solo` : "양망두_Solo");
  const [chzzkEntry, setChzzkEntry] = useState("https://chzzk.naver.com/b3e262a2795f17734c149afc738ad250");
  const [localFilePath, setLocalFilePath] = useState("");
  const [vodList, setVodList] = useState<VODRow[]>([]);
  const [selectedVodNo, setSelectedVodNo] = useState<string>("");
  const [isScanning, setIsScanning] = useState(false);
  const [isFetchingVods, setIsFetchingVods] = useState(false);
  const [lastGeneratedFolder, setLastGeneratedFolder] = useState<string>("");

  const handleFetchChzzkVods = async () => {
    const targetUrl = chzzkEntry || "https://chzzk.naver.com/b3e262a2795f17734c149afc738ad250";
    setIsFetchingVods(true);
    addLog(`[치지직 탐색] 네이버 치지직 라이브 API 호출 중: ${targetUrl}`, "INFO");

    try {
      const liveItems: ChzzkVideoItem[] = await invoke("fetch_chzzk_vod_catalog", { channelTarget: targetUrl });
      
      const rows: VODRow[] = await Promise.all(
        liveItems.map(async (item) => {
          const [stText, stFg, stBg, fPath]: [string, string, string, string] = await invoke("check_vod_status", {
            channelName: scanStreamerPreset || "양망두",
            videoNo: item.video_no,
            dateStr: item.date_str,
            title: item.title,
          });
          return {
            video_no: item.video_no,
            title: item.title,
            date_str: item.date_str,
            duration_str: item.duration_str,
            status_text: stText,
            status_fg: stFg,
            status_bg: stBg,
            folder_path: fPath,
            vod_url: item.vod_url,
          };
        })
      );

      setVodList(rows);
      if (rows.length > 0) {
        setSelectedVodNo(rows[0].video_no);
      }
      addLog(`✓ 네이버 치지직 API 연동 성공: '${scanStreamerPreset || "양망두"}' (실제 VOD ${rows.length}편 로드 완료)`, "SUCCESS");
    } catch (e) {
      addLog(`치지직 VOD 조회 오류: ${e}`, "ERROR");
    } finally {
      setIsFetchingVods(false);
    }
  };

  const handleOpenChzzkVideo = (videoNo: string, vodUrl?: string) => {
    const targetUrl = vodUrl || (videoNo.startsWith("http") ? videoNo : `https://chzzk.naver.com/video/${videoNo}`);
    addLog(`🌐 치지직 영상 열기: ${targetUrl}`, "INFO");
    invoke("open_external_url", { url: targetUrl }).catch((err) => addLog(`브라우저 열기 오류: ${err}`, "ERROR"));
  };

  const handleSelectLocalFile = async () => {
    try {
      const selectedPath: string | null = await invoke("select_video_file");
      if (selectedPath) {
        setLocalFilePath(selectedPath);
        addLog(`📁 로컬 영상 파일 선택됨: ${selectedPath}`, "SUCCESS");
      }
    } catch (err) {
      addLog(`파일 선택 오류: ${err}`, "ERROR");
    }
  };

  const handleStartScan = async () => {
    const targetInput = sourceMode === "local" ? localFilePath.trim() : selectedVodNo;
    if (!targetInput) {
      addLog("스캔할 대상을 지정해 주세요.", "ERROR");
      return;
    }

    const selectedItem = vodList.find((v) => v.video_no === selectedVodNo);
    const targetTitle = sourceMode === "local" ? localFilePath.split(/[\\/]/).pop() || "로컬 영상" : selectedItem?.title || "VOD";

    setIsScanning(true);
    setProgress({ pct: 20, msg: "오디오 스트림 수신 및 Whisper STT 모델 로드 중..." });
    addLog(`⚡ [타임라인 정밀 스캔 가동] 스트리머: '${scanStreamerPreset || "양망두"}' | DNA 스타일: '${selectedDnaStyle}' | 대상: ${targetTitle}`, "INFO");

    let ticker: any = null;
    try {
      let currentPct = 25;
      const stages = [
        "1k~3.5k 오디오 텐션 궤적 및 도파민 피크 분석 중...",
        "32-pt 그래프 기승전결 형상 유사도 C-JIT 매칭 중...",
        "VAD 침묵 감지 및 대화 호흡 단위 인/아웃 스내핑 중...",
        "Whisper STT 초벌 자막 생성 및 화자 분리(Diarization) 중...",
        "Kiwi 한국어 문장 종결 보정 및 프리미어 60fps XML 패키징 중...",
      ];
      let stageIdx = 0;
      ticker = setInterval(() => {
        currentPct = Math.min(96, currentPct + Math.floor(Math.random() * 4) + 2);
        stageIdx = (stageIdx + 1) % stages.length;
        setProgress({ pct: currentPct, msg: stages[stageIdx] + " (" + currentPct + "%)" });
      }, 2500);

      const scanStdout: string = await invoke("start_vod_timeline_scan", {
        vodUrlOrNo: targetInput,
        streamerName: scanStreamerPreset || "양망두",
        dnaProfileName: selectedDnaStyle,
      });

      if (ticker) clearInterval(ticker);

      let finalPackageDir = "";
      for (const line of (scanStdout || "").split("\n")) {
        try {
          const parsed = JSON.parse(line.trim());
          if (parsed.type === "scan_complete" && parsed.package_folder) {
            finalPackageDir = parsed.package_folder;
          }
        } catch {
          // ignore non-json lines
        }
      }

      if (finalPackageDir) {
        setLastGeneratedFolder(finalPackageDir);
      }

      setProgress({ pct: 100, msg: "타임라인 스캔 & XML/SRT 패키지 생성 완료" });
      addLog(`🎉 [스캔 완료] '${targetTitle}' XML/SRT 가편집 패키지 생성 완료!`, "SUCCESS");

      // Refresh list status
      if (sourceMode === "chzzk") {
        handleFetchChzzkVods();
      }
    } catch (e) {
      if (ticker) clearInterval(ticker);
      addLog(`스캔 실패: ${e}`, "ERROR");
      setProgress({ pct: 0, msg: "스캔 오류 발생" });
    } finally {
      setIsScanning(false);
    }
  };

  const handleOpenFolder = async (folderPath: string) => {
    try {
      await invoke("open_folder", { folderPath });
      addLog(`📂 결과 폴더 열기 성공: ${folderPath}`, "SUCCESS");
    } catch (err) {
      addLog(`폴더 열기 오류: ${err}`, "ERROR");
    }
  };

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="border-b border-[#1E2638] pb-2">
        <h2 className="text-sm font-bold text-[#00E5FF] flex items-center gap-2">
          <PlayCircle className="w-4 h-4" /> 🎯 3. VOD 풀영상 타임라인 정밀 스캔 & 3단 서사 가편집 생성 (VOD Timeline Scanner)
        </h2>
        <p className="text-[11px] text-slate-400 mt-0.5">
          • 네이버 치지직 지난 방송 VOD 또는 내 PC의 영상 파일(.mp4, .ts, .mkv)을 초고속 스캔합니다.
          <br />• 채널 고유의 DNA 곡선(ASL, 텐션 궤적)과 매칭하여 60fps 마스터 XML + 화자 분리 초벌 자막(SRT)을 30초 내에 패키징합니다.
        </p>
      </div>

      {/* Preset Streamer & DNA Selection */}
      <div className="bg-[#111622] border border-[#1E2638] rounded-lg p-3 flex flex-col gap-2.5">
        <div className="grid grid-cols-12 gap-3 items-center">
          <div className="col-span-6 flex items-center gap-2">
            <span className="font-bold text-slate-200 text-xs w-28">👤 분석 스트리머:</span>
            <select
              value={scanStreamerPreset}
              onChange={(e) => {
                const sName = e.target.value;
                setScanStreamerPreset(sName);
                setSelectedDnaStyle(`${sName}_Solo`);
              }}
              className="flex-1 bg-[#161C2A] border border-[#1E2638] rounded px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-[#00E5FF]"
            >
              {streamers.map((s) => (
                <option key={s} value={s}>
                  {s} (등록된 프로필)
                </option>
              ))}
            </select>
          </div>

          <div className="col-span-6 flex items-center gap-2">
            <span className="font-bold text-slate-200 text-xs w-28">🧬 적용 DNA 스타일:</span>
            <select
              value={selectedDnaStyle}
              onChange={(e) => setSelectedDnaStyle(e.target.value)}
              className="flex-1 bg-[#161C2A] border border-[#1E2638] rounded px-3 py-1.5 text-xs text-[#00E5FF] font-bold focus:outline-none focus:border-[#00E5FF]"
            >
              <option value={`${scanStreamerPreset}_Solo`}>🎯 {scanStreamerPreset}_Solo (솔로 텐션 & 심리학 호흡)</option>
              <option value={`${scanStreamerPreset}_Collab`}>👥 {scanStreamerPreset}_Collab (합방 텐션 & 심리학 빠른 컷)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Target Source Selection Card */}
      <div className="bg-[#111622] border border-[#1E2638] rounded-lg p-3 flex flex-col gap-2.5 text-xs">
        {/* Row 1: Source Radio Buttons */}
        <div className="flex items-center gap-6 pb-2 border-b border-[#1E2638]/60">
          <span className="font-bold text-slate-300">스캔 소스 선택:</span>
          <label className="flex items-center gap-1.5 cursor-pointer text-slate-200 font-semibold">
            <input
              type="radio"
              name="sourceMode"
              checked={sourceMode === "chzzk"}
              onChange={() => setSourceMode("chzzk")}
              className="accent-[#00E5FF] cursor-pointer"
            />
            <Radio className="w-3.5 h-3.5 text-[#00E5FF]" /> 치지직 지난 방송 VOD (URL/채널)
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer text-slate-200 font-semibold">
            <input
              type="radio"
              name="sourceMode"
              checked={sourceMode === "local"}
              onChange={() => setSourceMode("local")}
              className="accent-[#00E5FF] cursor-pointer"
            />
            <FileVideo className="w-3.5 h-3.5 text-[#FFD700]" /> 내 PC 로컬 영상 파일 (.mp4, .ts, .mkv)
          </label>
        </div>

        {/* Row 2: Input Field according to Source Mode */}
        {sourceMode === "chzzk" ? (
          <div className="grid grid-cols-12 gap-2 items-center">
            <span className="col-span-2 font-bold text-[#80D8FF]">📡 치지직 방송 주소:</span>
            <input
              type="text"
              placeholder="https://chzzk.naver.com/... 또는 채널ID 32자리 입력"
              value={chzzkEntry}
              onChange={(e) => setChzzkEntry(e.target.value)}
              className="col-span-8 bg-[#161C2A] border border-[#1E2638] rounded px-3 py-1.5 text-slate-200 focus:outline-none focus:border-[#00E5FF]"
            />
            <button
              disabled={isFetchingVods}
              onClick={handleFetchChzzkVods}
              className="col-span-2 py-1.5 rounded bg-[#00897B] hover:bg-[#00695C] text-white font-bold flex items-center justify-center gap-1.5 shadow-md cursor-pointer"
            >
              🔍 {isFetchingVods ? "조회 중..." : "지난 방송 조회"}
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-12 gap-2 items-center">
            <span className="col-span-2 font-bold text-[#FFD700]">📁 로컬 영상 파일:</span>
            <div className="col-span-8 bg-[#161C2A] border border-[#1E2638] rounded px-3 py-1.5 text-slate-200 truncate flex items-center">
              {localFilePath ? (
                <span className="text-[#FFD700] font-mono">{localFilePath}</span>
              ) : (
                <span className="text-slate-500">우측 [파일 열기] 버튼을 눌러 영상을 선택하세요.</span>
              )}
            </div>
            <button
              onClick={handleSelectLocalFile}
              className="col-span-2 py-1.5 rounded bg-[#F57F17] hover:bg-[#F57C00] text-white font-bold flex items-center justify-center gap-1.5 shadow-md cursor-pointer transition-transform active:scale-95"
            >
              <Upload className="w-3.5 h-3.5" /> 📂 파일 열기
            </button>
          </div>
        )}

        {/* Row 3: Scan Action Buttons */}
        <div className="flex items-center justify-between pt-1 border-t border-[#1E2638]/50">
          <span className="text-[#00E5FF] font-bold text-xs">
            {sourceMode === "chzzk"
              ? selectedVodNo
                ? `🎯 선택됨: 치지직 VOD #${selectedVodNo} (${vodList.find((v) => v.video_no === selectedVodNo)?.title?.slice(0, 30)}...)`
                : "👉 방송 목록에서 스캔할 VOD를 선택하세요."
              : localFilePath
              ? `🎯 선택됨: 로컬 파일 (${localFilePath.split(/[\\/]/).pop()})`
              : "👉 [파일 열기]를 눌러 분석할 로컬 영상 파일을 선택하세요."}
          </span>
          <div className="flex items-center gap-2">
            <button
              disabled={isScanning || (sourceMode === "chzzk" ? !selectedVodNo : !localFilePath.trim())}
              onClick={handleStartScan}
              className="px-4 py-1.5 rounded bg-[#0288D1] hover:bg-[#0277BD] text-white font-bold flex items-center gap-1.5 shadow-md transition-all active:scale-95 cursor-pointer disabled:opacity-50"
            >
              <Zap className="w-3.5 h-3.5" />
              {isScanning ? "타임라인 정밀 분석 중..." : "⚡ 타임라인 정밀 스캔 시작"}
            </button>
            <button
              onClick={() => handleOpenFolder(lastGeneratedFolder || `markers/${scanStreamerPreset || "양망두"}`)}
              className="px-3 py-1.5 rounded bg-[#1E2638] hover:bg-[#2D3A54] text-slate-200 flex items-center gap-1 cursor-pointer"
            >
              <FolderOpen className="w-3.5 h-3.5" /> 📁 결과 폴더 열기
            </button>
          </div>
        </div>
      </div>

      {/* VOD Table (Only in Chzzk mode) */}
      {sourceMode === "chzzk" ? (
        <div className="h-64 overflow-y-auto border border-[#1E2638] rounded-lg bg-[#0E121B] text-xs">
          {vodList.map((row) => (
            <div
              key={row.video_no}
              onClick={() => setSelectedVodNo(row.video_no)}
              className={`flex items-center justify-between p-2.5 border-b border-[#1E2638]/40 cursor-pointer transition-colors ${
                selectedVodNo === row.video_no ? "bg-[#143142] border-l-4 border-l-[#00E5FF]" : "hover:bg-[#182030]"
              }`}
            >
              <div className="flex items-center gap-2">
                <input
                  type="radio"
                  checked={selectedVodNo === row.video_no}
                  onChange={() => setSelectedVodNo(row.video_no)}
                  className="accent-[#00E5FF] mr-1 cursor-pointer"
                />
                <span className="px-2 py-0.5 rounded text-[10px] font-bold" style={{ color: row.status_fg, backgroundColor: row.status_bg }}>
                  {row.status_text}
                </span>
                <span className="text-[#90CAF9] bg-[#102538] px-2 py-0.5 rounded text-[10px]">📅 {row.date_str}</span>
                <span className="text-[#CE93D8] bg-[#2A1733] px-2 py-0.5 rounded text-[10px]">⏱ {row.duration_str}</span>
                <span
                  onClick={(e) => {
                    e.stopPropagation();
                    handleOpenChzzkVideo(row.video_no, row.vod_url);
                  }}
                  className="font-bold text-slate-200 hover:text-[#00E5FF] hover:underline cursor-pointer ml-1 inline-flex items-center gap-1.5 transition-colors group"
                  title="클릭하여 치지직 원본 영상 페이지 열기"
                >
                  🎬 {row.title}
                  <ExternalLink className="w-3 h-3 text-[#00E5FF] opacity-50 group-hover:opacity-100 transition-opacity" />
                </span>
              </div>
              {row.folder_path && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleOpenFolder(row.folder_path);
                  }}
                  className="text-[10px] font-bold text-slate-300 bg-[#1E293B] hover:bg-[#334155] px-2.5 py-1 rounded flex items-center gap-1 cursor-pointer"
                >
                  <FolderOpen className="w-3 h-3" /> 폴더 열기
                </button>
              )}
            </div>
          ))}
          {vodList.length === 0 && (
            <div className="py-16 text-center text-slate-500 flex flex-col items-center gap-2">
              <AlertTriangle className="w-6 h-6 text-slate-600" />
              <span>조회된 방송이 없습니다. 상단에서 [지난 방송 조회]를 눌러주세요.</span>
            </div>
          )}
        </div>
      ) : (
        <div className="h-64 border border-dashed border-[#1E2638] rounded-lg bg-[#0E121B] flex flex-col items-center justify-center p-6 text-center text-xs text-slate-400 gap-3">
          <FileVideo className="w-12 h-12 text-[#FFD700]/70" />
          <div className="flex flex-col gap-1">
            <span className="font-bold text-slate-200 text-sm">내 컴퓨터에 저장된 영상 파일 스캔</span>
            <span>상단의 <span className="text-[#FFD700] font-semibold">[📂 파일 열기]</span> 버튼을 눌러 녹화된 방송 원본 파일(.mp4, .ts, .mkv)을 선택하세요.</span>
            <span className="text-slate-500 text-[11px] mt-1">• 선택 후 [⚡ 타임라인 정밀 스캔 시작]을 누르면 프리미어·리졸브 XML + 초벌 자막 SRT + 안내문서가 자동 생성됩니다.</span>
          </div>
        </div>
      )}
    </div>
  );
};



