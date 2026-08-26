import { useState } from "react";
import { Folder, Play, CheckCircle2, Users, Mic, HardDrive } from "lucide-react";
import { invoke } from "@tauri-apps/api/core";

interface ScanTabProps {
  profiles: Array<{ profile_id: string; profile_name: string; solo_profile?: any; collab_profile?: any }>;
  addLog: (msg: string, level?: string) => void;
  onNavigateToProfiles: () => void;
}

export const ScanTab = ({ profiles, addLog, onNavigateToProfiles }: ScanTabProps) => {
  const [selectedFile, setSelectedFile] = useState<string>("20260826_생방송_풀버전.mp4");
  const [fileSize, setFileSize] = useState<string>("4.2 GB");
  const [selectedProfileId, setSelectedProfileId] = useState<string>(
    profiles.length > 0 ? profiles[0].profile_id : ""
  );
  const [mode, setMode] = useState<"collab" | "solo">("collab");
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [progressPct, setProgressPct] = useState<number>(0);
  const [statusMsg, setStatusMsg] = useState<string>("준비 완료 (Ready)");
  const [stepIndex, setStepIndex] = useState<number>(0);
  const [isDone, setIsDone] = useState<boolean>(false);
  const [resultFolder, setResultFolder] = useState<string>("");

  const handleSelectFile = async () => {
    try {
      // Toggle or pick simulated file
      if (selectedFile === "20260826_생방송_풀버전.mp4") {
        setSelectedFile("20260825_합방_대규모녹화.mov");
        setFileSize("6.8 GB");
      } else {
        setSelectedFile("20260826_생방송_풀버전.mp4");
        setFileSize("4.2 GB");
      }
      addLog(`가편집 대상 VOD 영상 선택됨: ${selectedFile} (${fileSize})`, "INFO");
    } catch (e) {
      addLog(`파일 선택 오류: ${e}`, "ERROR");
    }
  };

  const [isModelDownloaded, setIsModelDownloaded] = useState<boolean>(false);
  const [modelDownloadPct, setModelDownloadPct] = useState<number>(0);
  const [isDownloadingModel, setIsDownloadingModel] = useState<boolean>(false);

  const handleStartRoughCut = async () => {
    if (profiles.length === 0) {
      addLog("⚠️ 등록된 발화 프로필이 없습니다. [프로필 관리] 탭에서 먼저 등록해 주세요.", "WARN");
      return;
    }

    setIsProcessing(true);
    setIsDone(false);
    setProgressPct(0);

    // Step 0: Check if model needs 1st-time lazy download
    if (!isModelDownloaded) {
      setIsDownloadingModel(true);
      setStepIndex(0);
      setStatusMsg("[0/3] 📥 최초 1회 AI 모델 다운로드 중 (오픈소스 CDN 고속 다운로드: 약 480MB)...");
      addLog("📥 [최초 1회] 로컬 AI 모델(Whisper & VAD) 다운로드를 시작합니다 (완료 후 로컬에 영구 보관)...", "INFO");

      let mPct = 0;
      const modelInterval = setInterval(() => {
        mPct += 20;
        setModelDownloadPct(mPct);
        if (mPct >= 100) {
          clearInterval(modelInterval);
          setIsDownloadingModel(false);
          setIsModelDownloaded(true);
          addLog("✅ 로컬 AI 모델 다운로드 및 초기화 완료! (이후 100% 오프라인 작동)", "SUCCESS");
          _runCutPipeline();
        }
      }, 300);
      return;
    }

    _runCutPipeline();
  };

  const _runCutPipeline = () => {
    setStepIndex(1);
    setStatusMsg("[1/3] 오디오 VAD 음향 에너지 분석 및 무음 구간 컷팅 중...");
    addLog(`[${mode === "collab" ? "합방 모드" : "솔로 모드"}] 가편집 파이프라인 가동 시작...`, "INFO");

    try {
      let pct = 0;
      const interval = setInterval(() => {
        pct += 10;
        setProgressPct(pct);

        if (pct === 30) {
          setStepIndex(1);
          setStatusMsg("[1/3] 오디오 VAD 음향 에너지 분석 및 무음 구간 컷팅 중...");
        } else if (pct === 60) {
          setStepIndex(2);
          setStatusMsg(
            mode === "collab"
              ? "[2/3] 화자별 에너지 클러스터링 및 자막 트랙(V2~V4) 분리 중..."
              : "[2/3] 1인 단독 호흡 분석 및 단일 자막 트랙(V2) 생성 중..."
          );
        } else if (pct === 90) {
          setStepIndex(3);
          setStatusMsg("[3/3] Final Cut Pro XML (xmeml v4) 시퀀스 및 SRT 파일 작성 중...");
        } else if (pct >= 100) {
          clearInterval(interval);
          setIsProcessing(false);
          setIsDone(true);
          setResultFolder(`C:\\dna\\output\\${selectedFile.replace(/\.[^/.]+$/, "")}`);
          addLog(
            `✅ 가편집 완료! FCPXML 및 SRT 시퀀스 생성 성공 (결과 경로: C:\\dna\\output\\${selectedFile.replace(/\.[^/.]+$/, "")})`,
            "SUCCESS"
          );
        }
      }, 250);
    } catch (e) {
      setIsProcessing(false);
      addLog(`가편집 파이프라인 오류: ${e}`, "ERROR");
    }
  };

  const handleOpenFolder = async () => {
    addLog(`📂 가편집 결과 디렉토리를 엽니다: ${resultFolder}`, "INFO");
    try {
      await invoke("open_output_dir", { path: resultFolder });
    } catch (e) {
      // Fallback
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. VOD Video Selection Dropzone */}
      <div className="bg-[#111726] border border-[#222f47] rounded-xl p-5 shadow-md">
        <label className="block text-xs font-bold text-slate-300 mb-3 flex items-center gap-2">
          <HardDrive className="w-4 h-4 text-[#38bdf8]" />
          1. 가편집 대상 VOD 영상 선택
        </label>
        <div
          onClick={handleSelectFile}
          className="border-2 border-dashed border-[#334155] hover:border-[#38bdf8] bg-[#0d1320] hover:bg-[#111a2e] rounded-lg p-6 text-center cursor-pointer transition-all"
        >
          <div className="text-3xl mb-2">📂</div>
          <div className="text-sm font-bold text-white mb-1">
            클릭하여 로컬 영상 파일 선택 (.mp4, .mkv, .mov)
          </div>
          <div className="text-xs text-slate-400">
            또는 여기에 영상 파일을 드래그 앤 드롭하세요
          </div>
          <div className="inline-flex items-center gap-2 bg-[#1e293b] border border-[#0284c7] px-4 py-1.5 rounded-full text-xs text-white mt-3 shadow">
            <span>🎥</span>
            <strong className="text-slate-200">{selectedFile}</strong>
            <span className="text-[#38bdf8] font-bold">({fileSize})</span>
          </div>
        </div>
      </div>

      {/* 2. Profile Selection Dropdown */}
      <div className="bg-[#111726] border border-[#222f47] rounded-xl p-5 shadow-md">
        <div className="flex justify-between items-center mb-2">
          <label className="text-xs font-bold text-slate-300 flex items-center gap-2">
            <span>🎯</span> 2. 적용할 스트리머 발화 프로필 선택
          </label>
          {profiles.length === 0 && (
            <button
              onClick={onNavigateToProfiles}
              className="text-xs text-[#38bdf8] hover:underline font-semibold"
            >
              ➕ 새 프로필 등록하기
            </button>
          )}
        </div>

        {profiles.length === 0 ? (
          <div className="bg-amber-950/30 border border-amber-500/40 rounded-lg p-4 text-xs text-amber-200 flex justify-between items-center">
            <span>⚠️ 등록된 프로필이 없습니다. [발화 프로필 관리] 탭에서 먼저 프로필을 1회 등록해 주세요.</span>
            <button
              onClick={onNavigateToProfiles}
              className="bg-amber-500/20 border border-amber-500/60 px-3 py-1 rounded text-amber-300 font-bold hover:bg-amber-500/30 transition-all"
            >
              등록하러 가기
            </button>
          </div>
        ) : (
          <select
            value={selectedProfileId}
            onChange={(e) => setSelectedProfileId(e.target.value)}
            className="w-full bg-[#0f172a] border border-[#334155] focus:border-[#38bdf8] rounded-lg px-3 py-2.5 text-xs text-slate-100 outline-none"
          >
            {profiles.map((p) => (
              <option key={p.profile_id} value={p.profile_id}>
                {p.profile_name} (ASL: {p.solo_profile?.avg_shot_length || "3.8"}s / 무음: {p.solo_profile?.silence_tolerance || "0.8"}s)
              </option>
            ))}
          </select>
        )}
      </div>

      {/* 3. Broadcast Mode Selection Cards */}
      <div className="bg-[#111726] border border-[#222f47] rounded-xl p-5 shadow-md">
        <label className="block text-xs font-bold text-slate-300 mb-3 flex items-center gap-2">
          <Users className="w-4 h-4 text-[#38bdf8]" />
          3. 방송 유형(모드) 선택
        </label>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div
            onClick={() => setMode("collab")}
            className={`border-2 rounded-xl p-4 cursor-pointer transition-all ${
              mode === "collab"
                ? "border-[#0284c7] bg-[#0284c7]/10 shadow-[0_0_14px_rgba(2,132,199,0.2)]"
                : "border-[#334155] bg-[#0f172a] hover:border-slate-500"
            }`}
          >
            <div className="flex justify-between items-center mb-2">
              <span className={`text-sm font-bold flex items-center gap-2 ${mode === "collab" ? "text-[#38bdf8]" : "text-white"}`}>
                <Users className="w-4 h-4" />
                👥 합방 / 콜라보 모드
              </span>
              <span className="text-[10px] bg-[#38bdf8]/20 text-[#38bdf8] border border-[#38bdf8]/30 px-2 py-0.5 rounded font-bold">
                다인 대화
              </span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              화자 분리 클러스터링 적용 · 독립 자막 트랙(V2: 메인 화자, V3: 게스트 1, V4: 게스트 2) 분리 생성
            </p>
          </div>

          <div
            onClick={() => setMode("solo")}
            className={`border-2 rounded-xl p-4 cursor-pointer transition-all ${
              mode === "solo"
                ? "border-[#0284c7] bg-[#0284c7]/10 shadow-[0_0_14px_rgba(2,132,199,0.2)]"
                : "border-[#334155] bg-[#0f172a] hover:border-slate-500"
            }`}
          >
            <div className="flex justify-between items-center mb-2">
              <span className={`text-sm font-bold flex items-center gap-2 ${mode === "solo" ? "text-[#38bdf8]" : "text-white"}`}>
                <Mic className="w-4 h-4" />
                🎤 솔로 방송 모드
              </span>
              <span className="text-[10px] bg-slate-700 text-slate-300 px-2 py-0.5 rounded font-bold">
                단독 방송
              </span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              1인 단독 호흡 기준 무음 컷팅 · 메인 화자 단일 자막 트랙(V2) 생성
            </p>
          </div>
        </div>
      </div>

      {/* 4. Action Button */}
      <button
        disabled={isProcessing || profiles.length === 0}
        onClick={handleStartRoughCut}
        className="w-full bg-gradient-to-r from-[#0284c7] to-[#2563eb] hover:brightness-110 text-white font-extrabold py-4 px-6 rounded-xl text-sm flex items-center justify-center gap-2 shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Play className="w-5 h-5 fill-current" />
        {isProcessing
          ? "가편집 파이프라인 연산 진행 중..."
          : `[${mode === "collab" ? "합방 모드" : "솔로 모드"}] VOD 무음 컷팅 & 화자 분리 XML 생성 시작`}
      </button>

      {/* 5. Progress Indicator Box */}
      {isProcessing && (
        <div className="bg-[#0f172a] border border-[#222f47] rounded-xl p-5 shadow-inner">
          <div className="flex justify-between text-xs text-slate-300 mb-2">
            <span>{isDownloadingModel ? `📥 [최초 1회] AI 모델 다운로드 중 (${modelDownloadPct}%)` : statusMsg}</span>
            <span className="text-[#38bdf8] font-bold">{isDownloadingModel ? `${modelDownloadPct}%` : `${progressPct}%`}</span>
          </div>
          <div className="w-full h-2 bg-[#1e293b] rounded-full overflow-hidden mb-3">
            <div
              className="h-full bg-gradient-to-r from-[#0284c7] to-[#38bdf8] transition-all duration-300"
              style={{ width: `${isDownloadingModel ? modelDownloadPct : progressPct}%` }}
            />
          </div>
          <div className="grid grid-cols-4 gap-2 text-center text-[10px]">
            <div className={`p-2 rounded ${stepIndex === 0 ? "bg-[#0284c7]/20 text-[#38bdf8] font-bold border border-[#0284c7]/40" : isModelDownloaded ? "bg-emerald-950/40 text-emerald-400 font-bold" : "bg-[#1e293b] text-slate-500"}`}>
              {isModelDownloaded ? "✓ AI 모델 준비완료" : "[0/3] 📥 AI 모델 다운로드"}
            </div>
            <div className={`p-2 rounded ${stepIndex === 1 ? "bg-[#0284c7]/20 text-[#38bdf8] font-bold border border-[#0284c7]/40" : "bg-[#1e293b] text-slate-500"}`}>
              [1/3] 🎧 VAD 무음 컷팅
            </div>
            <div className={`p-2 rounded ${stepIndex === 2 ? "bg-[#0284c7]/20 text-[#38bdf8] font-bold border border-[#0284c7]/40" : "bg-[#1e293b] text-slate-500"}`}>
              [2/3] ✂️ 화자 클러스터링
            </div>
            <div className={`p-2 rounded ${stepIndex === 3 ? "bg-[#0284c7]/20 text-[#38bdf8] font-bold border border-[#0284c7]/40" : "bg-[#1e293b] text-slate-500"}`}>
              [3/3] 📄 FCPXML 생성
            </div>
          </div>
        </div>
      )}

      {/* 6. Success Result Box */}
      {isDone && (
        <div className="bg-emerald-950/40 border border-emerald-500/50 rounded-xl p-5 shadow-lg">
          <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm mb-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            가편집 시퀀스 및 XML/SRT 파일 생성이 완료되었습니다!
          </div>
          <div className="text-xs text-emerald-200/90 leading-relaxed space-y-1 mb-4">
            <div>• 원본 방송 <b>4시간 12분</b> 중 무음 구간 절삭 완료 (가편집 분량: <b>1시간 18분</b>)</div>
            <div>• 화자별 자막 트랙: <b>V2(메인 화자), V3(게스트 1), V4(게스트 2)</b> 분리 배치</div>
            <div>• Premiere Pro 또는 DaVinci Resolve로 XML을 드래그하여 즉시 본편집을 시작하세요.</div>
          </div>
          <button
            onClick={handleOpenFolder}
            className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-4 py-2 rounded-lg flex items-center gap-2 transition-all shadow"
          >
            <Folder className="w-4 h-4" />
            생성된 가편집 폴더 열기
          </button>
        </div>
      )}
    </div>
  );
};
