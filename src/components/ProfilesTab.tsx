import { useState } from "react";
import { Plus, Trash2, Youtube, Sparkles, CheckCircle, UserCheck, Inbox } from "lucide-react";

interface ProfileItem {
  profile_id: string;
  profile_name: string;
  chzzk_channel_url?: string;
  solo_profile?: any;
  collab_profile?: any;
  created_at?: string;
}

interface ProfilesTabProps {
  profiles: ProfileItem[];
  onRefreshProfiles: () => Promise<void>;
  addLog: (msg: string, level?: string) => void;
}

export const ProfilesTab = ({ profiles, onRefreshProfiles, addLog }: ProfilesTabProps) => {
  const [profileName, setProfileName] = useState<string>("");
  const [chzzkUrl, setChzzkUrl] = useState<string>("");
  const [soloLinks, setSoloLinks] = useState<string>("");
  const [collabLinks, setCollabLinks] = useState<string>("");
  const [isCalibrating, setIsCalibrating] = useState<boolean>(false);
  const [successBanner, setSuccessBanner] = useState<string>("");

  const handleCreateProfile = async () => {
    if (!profileName.trim()) {
      addLog("⚠️ 프로필 이름을 입력해 주세요.", "WARN");
      return;
    }

    const soloList = soloLinks
      .split("\n")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    const collabList = collabLinks
      .split("\n")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    if (soloList.length === 0 || collabList.length === 0) {
      addLog("⚠️ 솔로 링크와 합방 링크를 각각 1개 이상 입력해 주세요.", "WARN");
      return;
    }

    setIsCalibrating(true);
    setSuccessBanner("");
    addLog(`🔍 3+3 유튜브 링크 분석 및 발화 프로필 생성 시작: '${profileName}'`, "INFO");

    try {
      const resp = await fetch("/api/profiles/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile_name: profileName.trim(),
          chzzk_url: chzzkUrl.trim(),
          solo_urls: soloList,
          collab_urls: collabList,
        }),
      });

      if (resp.ok) {
        setProfileName("");
        setChzzkUrl("");
        setSoloLinks("");
        setCollabLinks("");
        await onRefreshProfiles();
        setIsCalibrating(false);
        setSuccessBanner(`✅ 발화 프로필 '${profileName}' 생성이 완료되었습니다.`);
        addLog(`✅ 프로필 '${profileName}' 생성 완료! (6개 유튜브 링크는 즉시 폐기됨)`, "SUCCESS");
      } else {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error || "서버 응답 오류");
      }
    } catch (e: any) {
      setIsCalibrating(false);
      setSuccessBanner("");
      addLog(`❌ 프로필 생성 실패: ${e.message}`, "ERROR");
      await onRefreshProfiles();
    }
  };

  const handleDeleteProfile = async (profileId: string, name: string) => {
    try {
      await fetch(`/api/profiles/${profileId}`, { method: "DELETE" });
      addLog(`🗑️ 프로필 '${name}' 삭제 완료`, "INFO");
      await onRefreshProfiles();
    } catch (e) {
      addLog(`프로필 삭제 오류: ${e}`, "ERROR");
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. New Profile Registration Form */}
      <div className="bg-[#111726] border border-[#222f47] rounded-xl p-6 shadow-md">
        <div className="flex items-center gap-2 text-sm font-bold text-white mb-4 pb-3 border-b border-[#222f47]">
          <Sparkles className="w-4 h-4 text-[#38bdf8]" />
          새 스트리머 프로필 등록
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-xs font-bold text-slate-300 mb-1.5">
              프로필 이름 (식별용 라벨)
            </label>
            <input
              type="text"
              placeholder="예: 메인 토크용, 게임 합방용 등 자유 입력"
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
              className="w-full bg-[#0a0f1d] border border-[#2d3748] rounded-lg px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-[#38bdf8]"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-300 mb-1.5">
              치지직 방송 채널 주소 (선택 입력)
            </label>
            <input
              type="text"
              placeholder="https://chzzk.naver.com/..."
              value={chzzkUrl}
              onChange={(e) => setChzzkUrl(e.target.value)}
              className="w-full bg-[#0a0f1d] border border-[#2d3748] rounded-lg px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-[#38bdf8]"
            />
          </div>
        </div>

        {/* 3+3 Youtube Links Inputs */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
          {/* Solo Broadcast 3 URLs */}
          <div className="bg-[#0a0f1d] border border-[#1e293b] rounded-lg p-3.5">
            <div className="flex items-center justify-between text-xs font-bold text-slate-200 mb-2">
              <div className="flex items-center gap-1.5 text-[#38bdf8]">
                <Youtube className="w-3.5 h-3.5 text-red-400" />
                단독 방송 유튜브 링크 3개
              </div>
              <span className="text-[10px] text-slate-400">줄바꿈으로 구분</span>
            </div>
            <textarea
              rows={3}
              placeholder="https://youtube.com/watch?v=...&#10;https://youtube.com/watch?v=...&#10;https://youtube.com/watch?v=..."
              value={soloLinks}
              onChange={(e) => setSoloLinks(e.target.value)}
              className="w-full bg-[#111726] border border-[#243048] rounded px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-[#38bdf8] font-mono leading-relaxed"
            />
            <p className="text-[10px] text-slate-400 mt-1">
              스트리머 단독 방송 편집본 링크를 입력하세요.
            </p>
          </div>

          {/* Collab Broadcast 3 URLs */}
          <div className="bg-[#0a0f1d] border border-[#1e293b] rounded-lg p-3.5">
            <div className="flex items-center justify-between text-xs font-bold text-slate-200 mb-2">
              <div className="flex items-center gap-1.5 text-[#c084fc]">
                <Youtube className="w-3.5 h-3.5 text-red-400" />
                합방 / 콜라보 유튜브 링크 3개
              </div>
              <span className="text-[10px] text-slate-400">줄바꿈으로 구분</span>
            </div>
            <textarea
              rows={3}
              placeholder="https://youtube.com/watch?v=...&#10;https://youtube.com/watch?v=...&#10;https://youtube.com/watch?v=..."
              value={collabLinks}
              onChange={(e) => setCollabLinks(e.target.value)}
              className="w-full bg-[#111726] border border-[#243048] rounded px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-[#38bdf8] font-mono leading-relaxed"
            />
            <p className="text-[10px] text-slate-400 mt-1">
              게스트와 함께 대화하며 방송한 편집본 링크를 입력하세요.
            </p>
          </div>
        </div>

        {/* Submit Button */}
        <button
          onClick={handleCreateProfile}
          disabled={isCalibrating}
          className="w-full bg-gradient-to-r from-[#0284c7] to-[#0ea5e9] hover:from-[#0369a1] hover:to-[#0284c7] disabled:opacity-50 text-white font-bold py-3 px-4 rounded-lg text-xs shadow-md transition-all flex items-center justify-center gap-2"
        >
          {isCalibrating ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              <span>유튜브 영상을 분석하고 있습니다... (수 초 소요)</span>
            </>
          ) : (
            <>
              <Plus className="w-4 h-4" />
              <span>유튜브 영상 분석하여 스트리머 프로필 만들기</span>
            </>
          )}
        </button>

        {successBanner && (
          <div className="mt-3 p-3 bg-emerald-950/40 border border-emerald-800/50 rounded-lg text-emerald-400 text-xs flex items-center gap-2">
            <CheckCircle className="w-4 h-4 flex-shrink-0" />
            <span>{successBanner}</span>
          </div>
        )}
      </div>

      {/* 2. Registered Profiles List */}
      <div className="bg-[#111726] border border-[#222f47] rounded-xl p-6 shadow-md">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-[#222f47]">
          <div className="flex items-center gap-2 text-sm font-bold text-white">
            <UserCheck className="w-4 h-4 text-[#10b981]" />
            내 등록 프로필 목록 ({profiles.length}개)
          </div>
          <span className="text-[11px] text-slate-400">개인 로컬 PC에만 안전하게 격리 보관됨</span>
        </div>

        {profiles.length === 0 ? (
          <div className="py-10 text-center flex flex-col items-center justify-center text-slate-500 bg-[#0a0f1d] rounded-lg border border-[#1e293b]">
            <Inbox className="w-8 h-8 text-slate-600 mb-2" />
            <p className="text-xs font-semibold text-slate-400">등록된 발화 프로필이 없습니다.</p>
            <p className="text-[11px] text-slate-500 mt-1">
              상단에서 프로필 이름과 유튜브 링크 6개를 입력하여 첫 프로필을 등록해 주세요.
            </p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {profiles.map((p) => (
              <div
                key={p.profile_id}
                className="bg-[#0a0f1d] border border-[#243048] rounded-lg p-3.5 flex items-center justify-between"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-white">{p.profile_name}</span>
                    {p.chzzk_channel_url && (
                      <span className="text-[10px] text-slate-500 font-mono">
                        ({p.chzzk_channel_url})
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleDeleteProfile(p.profile_id, p.profile_name)}
                  className="p-1.5 text-rose-400 hover:bg-rose-950/40 rounded transition-colors text-xs flex items-center gap-1"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>삭제</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
