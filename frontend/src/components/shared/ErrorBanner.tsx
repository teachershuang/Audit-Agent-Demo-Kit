interface ErrorBannerProps {
  message: string;
}

export function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
      {message}
    </div>
  );
}
