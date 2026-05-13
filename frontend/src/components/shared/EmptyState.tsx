import { FileSearch2 } from "lucide-react";

export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="glass-panel flex min-h-[320px] flex-col items-center justify-center rounded-[28px] border border-white/8 px-8 text-center">
      <div className="mb-4 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4 text-cyan-100">
        <FileSearch2 className="h-8 w-8" />
      </div>
      <h3 className="font-display text-2xl text-white">{title}</h3>
      <p className="mt-3 max-w-xl text-sm leading-7 text-slate-300">{description}</p>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="mt-6 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-5 py-2.5 text-sm font-medium text-cyan-100 transition hover:bg-cyan-400/20"
        >
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
