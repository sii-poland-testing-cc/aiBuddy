"use client";

interface InfoBannerProps {
  message: string;
  onDismiss?: () => void;
}

export default function InfoBanner({ message, onDismiss }: InfoBannerProps) {
  return (
    <div className="flex items-start gap-3 px-4 py-3 rounded-lg border bg-[#4a9e6b]/10 border-[#4a9e6b]/30 text-[#4a9e6b] animate-[fadeIn_0.2s_ease]">
      <span className="text-base leading-none shrink-0 mt-0.5">✓</span>
      <span className="flex-1 text-xs leading-relaxed">{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="shrink-0 text-[#4a9e6b]/60 hover:text-[#4a9e6b] transition-colors text-sm leading-none"
          aria-label="Zamknij"
        >
          ✕
        </button>
      )}
    </div>
  );
}
