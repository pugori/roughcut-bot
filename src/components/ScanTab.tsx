import { useState, useRef } from "react";
import { Folder, Play, CheckCircle2, Users, Mic, UploadCloud, AlertCircle } from "lucide-react";

interface ScanTabProps {
  profiles: Array<{ profile_id: string; profile_name: string; solo_profile?: any; collab_profile?: any }>;
  addLog: (msg: string, level?: string) => void;
  onGoToProfiles: () => void;
}

export const ScanTab = ({ profiles, addLog, onGoToProfiles }: ScanTabProps) => {
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [fileSize, setFileSize] = useState<string>("");
  const [selectedProfileId, setSelectedProfileId] = useState<string>(
    profiles.length > 0 ? profiles[0].profile_id : ""
  );
  const [mode, setMode] = useState<"collab" | "solo">("collab");
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [progressPct, setProgressPct] = useState<number>(0);
  const [statusMsg, setStatusMsg] = useState<string>("준비 완료");
  const [stepIndex, setStepIndex] = useState<number>(0);
const [isDone, setIsDone] = useState<boolean>(false);
  const [resultFolder, setResultFolder] = useState<string>("");
  const [exportXml, setExportXml] = useState<boolean>(true);
  const [exportFcpxml, setExportFcpxml] = useState<boolean>(true);
  const [exportSrt, setExportSrt] = useState<boolean>(true);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileClick = async () => {
    // @ts-ignore
    if (window.pywebview && window.pywebview.api) {
      try {
        // @ts-ignore
        const filepath = await window.pywebview.api.select_file();
        if (filepath) {
          setSelectedFile(filepath);
          setFileSize("로컬 파일");
          addLog(`선택된 파일: ${filepath}`, "INFO");
        }
      } catch (e) {
        console.error(e);
      }
    } else {
      fileInputRef.current?.click();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file.name);
      const sizeMb = file.size / (1024 * 1024);
      const sizeStr = sizeMb >= 1024 ? `${(sizeMb / 1024).toFixed(2)} GB` : `${sizeMb.toFixed(1)} MB`;
      setFileSize(sizeStr);
      addLog(`선택된 파일 (경로 제약 있음): ${file.name} (${sizeStr})`, "INFO");
    }
  };

  const [isModelDownloaded, setIsModelDownloaded] = useState<boolean>(false);
  const [modelDownloadPct, setModelDownloadPct] = useState<number>(0);
  const [isDownloadingModel, setIsDownloadingModel] = useState<boolean>(false);

  const handleStartRoughCut = async () => {
    if (!selectedFile) {
      addLog("⚠️ 먼저 가편집할 영상 파일을 선택해 주세요.", "WARN");
      return;
    }

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
      setStatusMsg("[0/3] 📥 최초 1회 AI 모델 다운로드 중 (약 2.5GB)...");
      addLog("📥 [최초 1회] 로컬 AI 모델 다운로드를 시작합니다 (진짜 다운로드 진행 중)...", "INFO");

      // 실제 API 호출
      fetch("/api/download_engine", { method: "POST" }).catch(e => console.error(e));

      const pollDownload = async () => {
        try {
          const res = await fetch("/api/download_engine/progress");
          const data = await res.json();
          setModelDownloadPct(data.pct);
          
          if (data.status === "done" || data.pct >= 100) {
            setIsDownloadingModel(false);
            setIsModelDownloaded(true);
            addLog("✅ 로컬 AI 모델 다운로드 완료! (이후 오프라인 작동)", "SUCCESS");
            _runCutPipeline();
            return;
          }
        } catch (e) {
          console.error(e);
        }
        setTimeout(pollDownload, 1000);
      };
      pollDownload();
      return;
    }

    _runCutPipeline();
  };

  const _runCutPipeline = async () => {
    setStepIndex(1);
    setStatusMsg("오디오 및 텐션 분석 준비 중...");
    addLog(
      `오디오 분석 시작 (모드: ${mode === "collab" ? "합방" : "솔로"})...`,
      "INFO"
    );

    try {
      const res = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video_path: selectedFile,
          profile_name: selectedProfileId,
          mode,
          export_xml: exportXml,
          export_fcpxml: exportFcpxml,
          export_srt: exportSrt,
        }),
      });
      const data = await res.json();
      if (!data.success) {
        addLog(`❌ 오류: ${data.error}`, "ERROR");
        setStatusMsg(`❌ ${data.error}`);
        setIsProcessing(false);
        return;
      }
    } catch (e) {
      addLog(`API 연결 실패: ${e}`, "ERROR");
      setStatusMsg(`API 연결 실패: ${e}`);
      setIsProcessing(false);
      return;
    }

    const pollProgress = async () => {
      try {
        const res = await fetch("/api/scan/progress");
        const data = await res.json();

        setProgressPct(data.pct);
        setStepIndex(data.step_index);
        setStatusMsg(data.status);

        if (data.done || data.status === "error" || data.error) {
          if (data.status === "error" || data.error) {
            addLog(`❌ 오류 발생: ${data.error || data.status}`, "ERROR");
            setStatusMsg(`❌ 오류: ${data.error || data.status}`);
            setIsProcessing(false);
          } else {
            setIsProcessing(false);
            setIsDone(true);
            setStatusMsg("✅ 편집 파일 생성이 완료되었습니다!");
            setResultFolder("output");
            addLog(
              `🎉 편집 파일 생성 완료! (저장 위치: 영상과 동일한 폴더)`,
              "SUCCESS"
            );
          }
          return; // Stop polling
        }
      } catch (e) {
        console.error(e);
      }
      setTimeout(pollProgress, 1000); // Schedule next poll only after current one finishes
    };
    pollProgress();
  };

  const handleOpenFolder = async () => {
    try {
      await fetch("/api/open_folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: resultFolder }),
      });
      addLog("📂 가편집 결과 폴더를 열었습니다.", "INFO");
    } catch (e) {
      addLog(`폴더 열기 오류: ${e}`, "ERROR");
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Target VOD File Dropzone */}
      <div className="bg-[#111726] border border-[#222f47] rounded-xl p-6 shadow-md">
        <label className="block text-xs font-bold text-slate-300 mb-2">
          📁 1. 가편집 대상 VOD 영상 선택
        </label>

        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept=".mp4,.mkv,.mov,.avi,.ts"
          className="hidden"
        />

        <div
          onClick={handleFileClick}
          className="border-2 border-dashed border-[#2d3748] hover:border-[#38bdf8] bg-[#0a0f1d] hover:bg-[#0e1628] rounded-xl p-8 text-center cursor-pointer transition-all duration-200"
        >
          <div className="flex flex-col items-center justify-center gap-2">
            <UploadCloud className="w-10 h-10 text-[#38bdf8] mb-1 animate-pulse" />
            <div className="text-sm font-bold text-white">
              {selectedFile ? selectedFile : "클릭하여 로컬 VOD 동영상 파일 선택"}
            </div>
            <div className="text-xs text-slate-400">
              {fileSize ? (
                <span className="text-[#38bdf8] font-bold">파일 용량: {fileSize}</span>
              ) : (
                "지원 포맷: .mp4, .mkv, .mov, .ts"
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 2. Streamer Profile Selection & 3. Broadcast Mode Selection */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Profile Selector */}
        <div className="bg-[#111726] border border-[#222f47] rounded-xl p-5 shadow-md">
          <label className="block text-xs font-bold text-slate-300 mb-2">
            🎯 2. 적용할 스트리머 발화 프로필 선택
          </label>
          {profiles.length > 0 ? (
            <select
              value={selectedProfileId}
              onChange={(e) => setSelectedProfileId(e.target.value)}
              className="w-full bg-[#0a0f1d] border border-[#2d3748] rounded-lg px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-[#38bdf8]"
            >
              {profiles.map((p) => (
                <option key={p.profile_id} value={p.profile_id}>
                  {p.profile_name}
                </option>
              ))}
            </select>
          ) : (
            <div className="p-3 bg-[#0a0f1d] border border-[#2d3748] rounded-lg text-xs text-slate-400 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-amber-400" />
                <span>등록된 프로필 없음</span>
              </div>
              <button
                onClick={onGoToProfiles}
                className="text-[#38bdf8] hover:underline font-bold"
              >
                + 프로필 등록하러 가기
              </button>
            </div>
          )}
        </div>

        {/* Mode Selector */}
        <div className="bg-[#111726] border border-[#222f47] rounded-xl p-5 shadow-md">
          <label className="block text-xs font-bold text-slate-300 mb-2">
            👥 3. 방송 유형(모드) 선택
          </label>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => setMode("collab")}
              className={`p-3 rounded-lg border text-left transition-all ${
                mode === "collab"
                  ? "bg-[#0c4a6e]/40 border-[#38bdf8] text-white"
                  : "bg-[#0a0f1d] border-[#1e293b] text-slate-400 hover:border-slate-600"
              }`}
            >
              <div className="flex items-center gap-1.5 text-xs font-bold mb-1">
                <Users className="w-3.5 h-3.5 text-[#38bdf8]" />
                합방 / 콜라보 모드
              </div>
              <p className="text-[10px] text-slate-400">화자별 다인 자막 트랙 분리</p>
            </button>

            <button
              onClick={() => setMode("solo")}
              className={`p-3 rounded-lg border text-left transition-all ${
                mode === "solo"
                  ? "bg-[#0c4a6e]/40 border-[#38bdf8] text-white"
                  : "bg-[#0a0f1d] border-[#1e293b] text-slate-400 hover:border-slate-600"
              }`}
            >
              <div className="flex items-center gap-1.5 text-xs font-bold mb-1">
                <Mic className="w-3.5 h-3.5 text-amber-400" />
                솔로 방송 모드
              </div>
              <p className="text-[10px] text-slate-400">1인 단독 호흡 기준 컷팅</p>
            </button>
          </div>
        </div>
      </div>

      {/* 3.5. Export Options */}
      <div className="bg-[#111726] border border-[#222f47] rounded-xl p-5 shadow-md">
        <label className="block text-xs font-bold text-slate-300 mb-3">
          🎯 4. 생성할 파일 형식 선택
        </label>
        <div className="flex gap-4">
          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input type="checkbox" checked={exportXml} onChange={(e) => setExportXml(e.target.checked)} className="rounded border-slate-600 bg-slate-800 text-[#38bdf8] focus:ring-[#38bdf8]" />
            프리미어 / 다빈치 리졸브 (.xml)
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input type="checkbox" checked={exportFcpxml} onChange={(e) => setExportFcpxml(e.target.checked)} className="rounded border-slate-600 bg-slate-800 text-[#38bdf8] focus:ring-[#38bdf8]" />
            파이널 컷 프로 (.fcpxml)
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input type="checkbox" checked={exportSrt} onChange={(e) => setExportSrt(e.target.checked)} className="rounded border-slate-600 bg-slate-800 text-[#38bdf8] focus:ring-[#38bdf8]" />
            개별 자막 파일 (.srt)
          </label>
        </div>
      </div>

      {/* 4. Action Button */}
      <button
        onClick={handleStartRoughCut}
        disabled={isProcessing || isDownloadingModel}
        className="w-full bg-gradient-to-r from-[#0284c7] to-[#0ea5e9] hover:from-[#0369a1] hover:to-[#0284c7] disabled:opacity-50 text-white font-extrabold py-4 px-6 rounded-xl text-sm shadow-lg transition-all flex items-center justify-center gap-2.5"
      >
        <Play className="w-4 h-4 fill-white" />
        <span>[{mode === "collab" ? "합방 모드" : "솔로 모드"}] 영상 자동 컷편집 시작하기</span>
      </button>

      {/* 5. Progress Section */}
      {(isProcessing || isDownloadingModel) && (
        <div className="bg-[#111726] border border-[#222f47] rounded-xl p-5 shadow-md space-y-3">
          <div className="flex items-center justify-between text-xs font-bold">
            <span className="text-slate-200">{statusMsg}</span>
            <span className="text-[#38bdf8]">{isDownloadingModel ? `${modelDownloadPct}%` : `${progressPct}%`}</span>
          </div>

          <div className="w-full h-2.5 bg-[#0a0f1d] rounded-full overflow-hidden border border-[#222f47]">
            <div
              className="h-full bg-gradient-to-r from-[#38bdf8] to-[#0284c7] transition-all duration-300"
              style={{ width: `${isDownloadingModel ? modelDownloadPct : progressPct}%` }}
            />
          </div>

          <div className="grid grid-cols-4 gap-2 pt-2 text-[11px]">
            <div className={`p-2 rounded border text-center ${stepIndex === 0 ? "bg-[#0c4a6e]/40 border-[#38bdf8] text-white" : "bg-[#0a0f1d] border-[#1e293b] text-slate-500"}`}>
              [0/3] AI 다운로드
            </div>
            <div className={`p-2 rounded border text-center ${stepIndex === 1 ? "bg-[#0c4a6e]/40 border-[#38bdf8] text-white" : "bg-[#0a0f1d] border-[#1e293b] text-slate-500"}`}>
              [1/3] 무음 구간 제거
            </div>
            <div className={`p-2 rounded border text-center ${stepIndex === 2 ? "bg-[#0c4a6e]/40 border-[#38bdf8] text-white" : "bg-[#0a0f1d] border-[#1e293b] text-slate-500"}`}>
              [2/3] 목소리 분류
            </div>
            <div className={`p-2 rounded border text-center ${stepIndex === 3 ? "bg-[#0c4a6e]/40 border-[#38bdf8] text-white" : "bg-[#0a0f1d] border-[#1e293b] text-slate-500"}`}>
              [3/3] 파일 완성
            </div>
          </div>
        </div>
      )}

      {/* 6. Completion Result Card */}
      {isDone && (
        <div className="bg-[#0f291e] border border-[#10b981]/40 rounded-xl p-5 shadow-lg flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="w-8 h-8 text-[#10b981] flex-shrink-0" />
            <div>
              <div className="text-sm font-bold text-white">자동 컷편집 파일 생성이 완료되었습니다!</div>
              <p className="text-xs text-emerald-300 mt-0.5">
                생성된 폴더 안의 편집 파일을 프리미어 프로나 다빈치 리졸브로 드래그해서 편집을 시작하세요.
              </p>
            </div>
          </div>
          <button
            onClick={handleOpenFolder}
            className="bg-[#10b981] hover:bg-[#059669] text-white font-bold py-2.5 px-4 rounded-lg text-xs shadow transition-all flex items-center gap-2 flex-shrink-0"
          >
            <Folder className="w-4 h-4" />
            <span>생성된 폴더 열기</span>
          </button>
        </div>
      )}
    </div>
  );
};
