import { LoaderCircle } from "lucide-react";

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center gap-4 rounded-[24px] border border-cyan-400/12 bg-slate-950/25">
      <LoaderCircle className="h-7 w-7 animate-spin text-cyan-300" />
      <p className="text-sm text-slate-300">{label}</p>
    </div>
  );
}
