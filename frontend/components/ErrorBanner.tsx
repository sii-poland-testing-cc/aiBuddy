"use client";

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
  onDismiss?: () => void;
}

export default function ErrorBanner({ message, onRetry, onDismiss }: ErrorBannerProps) {
  return (
    <div className="flex items-start gap-3 px-4 py-3 rounded-lg border bg-rose-500/10 border-rose-500/30 text-rose-400 animate-[fadeIn_0.2s_ease]">
      <span className="text-base leading-none shrink-0 mt-0.5">⚠️</span>
      <span className="flex-1 text-xs leading-relaxed">{message}</span>
      <div className="flex items-center gap-2 shrink-0">
        {onRetry && (
          <button
            onClick={onRetry}
            className="text-[11px] px-2 py-0.5 rounded border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 transition-colors font-medium"
          >
            Spróbuj ponownie
          </button>
        )}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-rose-400/60 hover:text-rose-400 transition-colors text-sm leading-none"
            aria-label="Zamknij"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}
