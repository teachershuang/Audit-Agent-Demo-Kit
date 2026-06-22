import { useEffect, useMemo, useState } from "react";
import { AnalysisWorkspace } from "./components/workspace/AnalysisWorkspace";
import { BaseWorkspace } from "./pages/BaseWorkspace";
import { api } from "./services/api";
import type { RuntimeModelProfileState } from "./types/base";

type WorkspaceMode = "analysis" | "base";

const WORKSPACE_KEY = "codex.workspace.mode";

function App() {
  const [workspace, setWorkspace] = useState<WorkspaceMode>("analysis");
  const [profileState, setProfileState] = useState<RuntimeModelProfileState | null>(null);
  const [switchingProfile, setSwitchingProfile] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const stored = window.localStorage.getItem(WORKSPACE_KEY);
    if (stored === "analysis" || stored === "base") {
      setWorkspace(stored);
    }
    void (async () => {
      try {
        const payload = await api.getRuntimeModelProfiles();
        setProfileState(payload);
      } catch (error) {
        setProfileError(error instanceof Error ? error.message : "模型档位加载失败");
      }
    })();
  }, []);

  const activeProfile = useMemo(
    () => profileState?.profiles.find((profile) => profile.id === profileState.currentProfileId) ?? null,
    [profileState],
  );

  function switchWorkspace(next: WorkspaceMode) {
    setWorkspace(next);
    window.localStorage.setItem(WORKSPACE_KEY, next);
  }

  async function switchModelProfile(profileId: string) {
    try {
      setSwitchingProfile(true);
      setProfileError(null);
      const payload = await api.switchRuntimeModelProfile(profileId);
      setProfileState(payload);
      setRefreshToken((value) => value + 1);
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : "模型切换失败");
    } finally {
      setSwitchingProfile(false);
    }
  }

  return (
    <div className="min-h-screen">
      <div className="fixed left-4 top-4 z-50 flex max-w-[calc(100vw-2rem)] flex-wrap items-center gap-2 rounded-[22px] border border-white/10 bg-slate-950/78 px-3 py-3 shadow-[0_22px_70px_rgba(2,8,23,0.55)] backdrop-blur-xl">
        <div className="mr-1 flex items-center gap-2">
          <button
            type="button"
            onClick={() => switchWorkspace("analysis")}
            className={`rounded-full px-4 py-2 text-sm transition ${
              workspace === "analysis"
                ? "border border-cyan-400/40 bg-cyan-400/12 text-cyan-50"
                : "border border-white/10 bg-slate-950/60 text-slate-200"
            }`}
          >
            合同解析工作台
          </button>
          <button
            type="button"
            onClick={() => switchWorkspace("base")}
            className={`rounded-full px-4 py-2 text-sm transition ${
              workspace === "base"
                ? "border border-cyan-400/40 bg-cyan-400/12 text-cyan-50"
                : "border border-white/10 bg-slate-950/60 text-slate-200"
            }`}
          >
            智能审查底座
          </button>
        </div>

        <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-2">
          <span className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/60">模型档位</span>
          <select
            value={profileState?.currentProfileId ?? "public"}
            onChange={(event) => void switchModelProfile(event.target.value)}
            disabled={switchingProfile || !profileState}
            className="rounded-full border border-white/10 bg-slate-950 px-3 py-1 text-sm text-slate-100 outline-none"
          >
            {(profileState?.profiles ?? []).map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.label}
              </option>
            ))}
          </select>
        </div>

        {activeProfile ? (
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-300">
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1">
              当前档位 {profileState?.currentProfileLabel}
            </span>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1">
              文本 {activeProfile.textModel}
            </span>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1">
              多模态 {activeProfile.visionModel || "未启用"}
            </span>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1">
              OCR {profileState?.paddleProbe?.status || activeProfile.ocrStrategy}
            </span>
          </div>
        ) : null}

        {switchingProfile ? <div className="text-xs text-cyan-100">正在切换模型链路...</div> : null}
        {profileError ? <div className="text-xs text-rose-200">{profileError}</div> : null}
      </div>

      {workspace === "analysis" ? (
        <AnalysisWorkspace refreshToken={refreshToken} />
      ) : (
        <BaseWorkspace refreshToken={refreshToken} />
      )}
    </div>
  );
}

export default App;
