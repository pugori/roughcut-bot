import { useState, useEffect } from "react";
import { Sliders, Sparkles, RefreshCw } from "lucide-react";

interface ChannelProfile {
  profile_id: string;
  channel_name: string;
  sample_count: number;
  avg_shot_length: number;
  tension_interval: number;
  silence_tolerance: number;
  highlight_rms_threshold: number;
  hook_duration: number;
  custom_vocab?: string;
  youtube_url?: string;
  chzzk_url?: string;
  profile_type: string;
  burst_cut_asl?: number;
  burst_min_duration?: number;
  sub_voice_boost?: number;
  speech_ratio_mean?: number;
}

interface ProfilesTabProps {
  streamers: string[];
  selectedStreamer: string;
  setSelectedStreamer: (s: string) => void;
  soloProfile: ChannelProfile | null;
  collabProfile: ChannelProfile | null;
  onRecalculateDna: () => void;
  onRefresh: () => void;
  addLog: (msg: string, level?: string) => void;
}

export const ProfilesTab = ({
  streamers,
  selectedStreamer,
  setSelectedStreamer,
  soloProfile,
  collabProfile,
  onRecalculateDna,
  onRefresh,
  addLog,
}: ProfilesTabProps) => {
  const [soloForm, setSoloForm] = useState({
    asl: "5.08",
    rms: "0.95",
    burstAsl: "2.50",
    burstDur: "4.00",
    subVoice: "1.20",
    speechRatio: "0.65",
  });

  const [collabForm, setCollabForm] = useState({
    asl: "7.54",
    rms: "1.10",
    burstAsl: "3.20",
    burstDur: "4.50",
    subVoice: "1.50",
    speechRatio: "0.70",
  });

  useEffect(() => {
    if (soloProfile) {
      setSoloForm({
        asl: soloProfile.avg_shot_length.toFixed(2),
        rms: soloProfile.highlight_rms_threshold.toFixed(2),
        burstAsl: (soloProfile.burst_cut_asl || 2.5).toFixed(2),
        burstDur: (soloProfile.burst_min_duration || 4.0).toFixed(2),
        subVoice: (soloProfile.sub_voice_boost || 1.2).toFixed(2),
        speechRatio: (soloProfile.speech_ratio_mean || 0.65).toFixed(2),
      });
    }
    if (collabProfile) {
      setCollabForm({
        asl: collabProfile.avg_shot_length.toFixed(2),
        rms: collabProfile.highlight_rms_threshold.toFixed(2),
        burstAsl: (collabProfile.burst_cut_asl || 3.2).toFixed(2),
        burstDur: (collabProfile.burst_min_duration || 4.5).toFixed(2),
        subVoice: (collabProfile.sub_voice_boost || 1.5).toFixed(2),
        speechRatio: (collabProfile.speech_ratio_mean || 0.70).toFixed(2),
      });
    }
  }, [soloProfile, collabProfile]);

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="border-b border-[#1E2638] pb-2">
        <h2 className="text-sm font-bold text-[#00E5FF] flex items-center gap-2">
          <Sliders className="w-4 h-4" /> 📊 2. 스트리머 투트랙 DNA 프로필 뷰어 (솔로 / 합방 분리 엔진)
        </h2>
        <p className="text-[11px] text-slate-400 mt-0.5">
          수집된 유튜브 영상 통계를 바탕으로 👤 1인 솔로용 및 👥 다인 합방용 2개 트랙의 편집 Baseline(DNA)을 제공합니다.
        </p>
      </div>

      {/* Streamer Selector Card */}
      <div className="bg-[#121622] border border-[#1E2638] rounded-lg p-3 flex items-center justify-between shadow-md">
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold text-slate-300">🎯 분석 대상 스트리머:</span>
          <select
            value={selectedStreamer}
            onChange={(e) => setSelectedStreamer(e.target.value)}
            className="bg-[#0E121B] border border-[#1E2638] rounded px-3 py-1.5 text-xs text-[#00E5FF] font-bold focus:outline-none focus:border-[#00E5FF] min-w-[200px]"
          >
            {streamers.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onRecalculateDna}
            className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-bold rounded bg-[#0288D1] hover:bg-[#0277BD] text-white shadow-md transition-all active:scale-95"
          >
            <Sparkles className="w-3.5 h-3.5" /> ⚡ DNA 재계산
          </button>
          <button
            onClick={onRefresh}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded bg-[#1E2638] hover:bg-[#2D3A54] text-slate-200"
          >
            <RefreshCw className="w-3.5 h-3.5" /> 🔄 목록 갱신
          </button>
        </div>
      </div>

      {/* Two-Track Cards Comparison Grid */}
      <div className="grid grid-cols-2 gap-4 flex-1 overflow-y-auto">
        {/* Solo Card */}
        <div className="bg-[#101726] border border-[#0D47A1] rounded-lg p-4 flex flex-col justify-between shadow-lg">
          <div>
            <div className="border-b border-[#0D47A1]/50 pb-2 mb-3">
              <h3 className="text-sm font-bold text-[#0288D1] flex items-center gap-2">👤 1인 단독 방송 DNA (Solo Mode)</h3>
              <p className="text-[11px] text-slate-400">• 빠른 호흡의 ASL & 집중된 오디오 텐션 컷</p>
            </div>

            {/* Form Fields */}
            <div className="flex flex-col gap-2 text-xs">
              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">⏱ 평균 컷 호흡 (ASL, 초)</div>
                  <div className="text-[10px] text-slate-400">단위: 초 (학습 영상 기반 정밀 통계)</div>
                </div>
                <input
                  type="text"
                  value={soloForm.asl}
                  onChange={(e) => setSoloForm({ ...soloForm, asl: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-[#00E5FF] font-mono font-bold"
                />
              </div>

              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">🔊 하이라이트 텐션 임계치</div>
                  <div className="text-[10px] text-slate-400">1k~3.5k 텐션 기반 데시벨 컷 오프</div>
                </div>
                <input
                  type="text"
                  value={soloForm.rms}
                  onChange={(e) => setSoloForm({ ...soloForm, rms: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-slate-200 font-mono"
                />
              </div>

              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">⚡ 빠른 호흡 버스트 구간 ASL</div>
                  <div className="text-[10px] text-slate-400">티키타카/폭소 구간 최소 컷 길이</div>
                </div>
                <input
                  type="text"
                  value={soloForm.burstAsl}
                  onChange={(e) => setSoloForm({ ...soloForm, burstAsl: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-slate-200 font-mono"
                />
              </div>

              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">⏳ 버스트 최소 유지 시간</div>
                  <div className="text-[10px] text-slate-400">단위: 초</div>
                </div>
                <input
                  type="text"
                  value={soloForm.burstDur}
                  onChange={(e) => setSoloForm({ ...soloForm, burstDur: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-slate-200 font-mono"
                />
              </div>

              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">🎙 서브 화자 감지 가중치</div>
                  <div className="text-[10px] text-slate-400">합방 참여자 음성 감지 민감도</div>
                </div>
                <input
                  type="text"
                  value={soloForm.subVoice}
                  onChange={(e) => setSoloForm({ ...soloForm, subVoice: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-slate-200 font-mono"
                />
              </div>

              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">🗣 음성 발화 밀도 (Speech Ratio)</div>
                  <div className="text-[10px] text-slate-400">전체 영상 중 오디오 유효 발화 비율</div>
                </div>
                <input
                  type="text"
                  value={soloForm.speechRatio}
                  onChange={(e) => setSoloForm({ ...soloForm, speechRatio: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-slate-200 font-mono"
                />
              </div>
            </div>
          </div>

          <button
            onClick={() => addLog(`✓ '${selectedStreamer}_Solo' (솔로) 프로필 파라미터가 수동 저장되었습니다.`, "SUCCESS")}
            className="w-full py-2 rounded bg-[#0288D1] hover:bg-[#0277BD] text-white text-xs font-bold mt-3 shadow-md"
          >
            💾 솔로 프로필 수동 저장
          </button>
        </div>

        {/* Collab Card */}
        <div className="bg-[#1A1226] border border-[#4A148C] rounded-lg p-4 flex flex-col justify-between shadow-lg">
          <div>
            <div className="border-b border-[#4A148C]/50 pb-2 mb-3">
              <h3 className="text-sm font-bold text-[#AB47BC] flex items-center gap-2">👥 다인 합방/대형 컨텐츠 DNA (Collab Mode)</h3>
              <p className="text-[11px] text-slate-400">• 여유로운 호흡의 ASL & 티키타카 음성 분리 컷</p>
            </div>

            {/* Form Fields */}
            <div className="flex flex-col gap-2 text-xs">
              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">⏱ 평균 컷 호흡 (ASL, 초)</div>
                  <div className="text-[10px] text-slate-400">단위: 초 (학습 영상 기반 정밀 통계)</div>
                </div>
                <input
                  type="text"
                  value={collabForm.asl}
                  onChange={(e) => setCollabForm({ ...collabForm, asl: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-[#AB47BC] font-mono font-bold"
                />
              </div>

              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">🔊 하이라이트 텐션 임계치</div>
                  <div className="text-[10px] text-slate-400">1k~3.5k 텐션 기반 데시벨 컷 오프</div>
                </div>
                <input
                  type="text"
                  value={collabForm.rms}
                  onChange={(e) => setCollabForm({ ...collabForm, rms: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-slate-200 font-mono"
                />
              </div>

              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">⚡ 빠른 호흡 버스트 구간 ASL</div>
                  <div className="text-[10px] text-slate-400">티키타카/폭소 구간 최소 컷 길이</div>
                </div>
                <input
                  type="text"
                  value={collabForm.burstAsl}
                  onChange={(e) => setCollabForm({ ...collabForm, burstAsl: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-slate-200 font-mono"
                />
              </div>

              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">⏳ 버스트 최소 유지 시간</div>
                  <div className="text-[10px] text-slate-400">단위: 초</div>
                </div>
                <input
                  type="text"
                  value={collabForm.burstDur}
                  onChange={(e) => setCollabForm({ ...collabForm, burstDur: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-slate-200 font-mono"
                />
              </div>

              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">🎙 서브 화자 감지 가중치</div>
                  <div className="text-[10px] text-slate-400">합방 참여자 음성 감지 민감도</div>
                </div>
                <input
                  type="text"
                  value={collabForm.subVoice}
                  onChange={(e) => setCollabForm({ ...collabForm, subVoice: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-slate-200 font-mono"
                />
              </div>

              <div className="flex justify-between items-center bg-[#121622] p-2 rounded border border-[#1E2638]">
                <div>
                  <div className="text-slate-200 font-bold">🗣 음성 발화 밀도 (Speech Ratio)</div>
                  <div className="text-[10px] text-slate-400">전체 영상 중 오디오 유효 발화 비율</div>
                </div>
                <input
                  type="text"
                  value={collabForm.speechRatio}
                  onChange={(e) => setCollabForm({ ...collabForm, speechRatio: e.target.value })}
                  className="w-20 bg-[#0E121B] border border-[#1E2638] rounded px-2 py-1 text-center text-slate-200 font-mono"
                />
              </div>
            </div>
          </div>

          <button
            onClick={() => addLog(`✓ '${selectedStreamer}_Collab' (합방) 프로필 파라미터가 수동 저장되었습니다.`, "SUCCESS")}
            className="w-full py-2 rounded bg-[#AB47BC] hover:bg-[#8E24AA] text-white text-xs font-bold mt-3 shadow-md"
          >
            💾 합방 프로필 수동 저장
          </button>
        </div>
      </div>
    </div>
  );
};
