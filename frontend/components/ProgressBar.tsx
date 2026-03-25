"use client";

interface ProgressBarProps {
  visible: boolean;
  /** 0.0–1.0; if omitted the bar shows at 60% (indeterminate) */
  progress?: number;
  message?: string;
}

export function ProgressBar({ visible, progress, message }: ProgressBarProps) {
  if (!visible) return null;
  const pct = progress !== undefined ? Math.round(progress * 100) : 60;
  return (
    <div
      className="flex-shrink-0 border-b border-buddy-border bg-buddy-surface flex items-center gap-3"
      style={{ padding: "8px 48px" }}
    >
      <div className="flex-1 bg-buddy-elevated rounded-full overflow-hidden" style={{ height: 4 }}>
        <div
          className="h-full bg-buddy-gold transition-all duration-300 rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      {message && (
        <span className="text-buddy-text-dim" style={{ fontSize: 11, flexShrink: 0 }}>
          {message}
        </span>
      )}
    </div>
  );
}
