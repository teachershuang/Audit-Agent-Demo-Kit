import { LoaderCircle } from "lucide-react";

interface LoadingStateProps {
  label: string;
  detail?: string;
  progress?: number;
}

export function LoadingState({ label, detail, progress }: LoadingStateProps) {
  const value = Math.max(0, Math.min(100, progress ?? 0));

  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center gap-4 rounded-[24px] border border-cyan-400/12 bg-slate-950/25">
      <LoaderCircle className="h-7 w-7 animate-spin text-cyan-300" />
      <div className="w-full max-w-[340px] space-y-3 px-6 text-center">
        <p className="text-sm text-slate-100">{label}</p>
        {detail ? <p className="text-xs leading-6 text-slate-400">{detail}</p> : null}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[11px] text-slate-500">
            <span>处理进度</span>
            <span>{value}%</span>
          </div>
          <div className="h-2 rounded-full bg-white/8">
            <div
              className="h-2 rounded-full bg-gradient-to-r from-cyan-400 to-sky-300 transition-all duration-500"
              style={{ width: `${value}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
