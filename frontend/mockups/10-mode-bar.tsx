/**
 * MOCKUP: ModeBar
 *
 * Central mode switcher, positioned top-center of the page header.
 * Replaces: Sidebar module switcher + PipelineSteps component
 *
 * Behavior:
 * - 3 tabs: Context Builder | Requirements | Suite Analyzer
 * - Requirements + Suite Analyzer are locked until contextReady=true
 * - Locked tabs show a small lock icon and tooltip
 * - Active tab has elevated background + gold accent dot below
 * - On mobile, uses short labels ("Context", "Reqs", "Analyzer")
 * - Switching modes is instant (no page navigation)
 */

export type Mode = "context" | "requirements" | "analyzer";

const MODES = [
  { id: "context" as const, label: "Context Builder", shortLabel: "Context" },
  { id: "requirements" as const, label: "Requirements", shortLabel: "Reqs" },
  { id: "analyzer" as const, label: "Suite Analyzer", shortLabel: "Analyzer" },
];

interface ModeBarProps {
  activeMode: Mode;
  onModeChange: (mode: Mode) => void;
  contextReady: boolean;
}

export default function ModeBarMockup({ activeMode = "context", contextReady = false }: Partial<ModeBarProps>) {
  return (
    <div className="flex items-center bg-buddy-surface border border-buddy-border rounded-xl p-1 gap-0.5">
      {MODES.map((m) => {
        const isActive = m.id === activeMode;
        const isLocked = m.id !== "context" && !contextReady;

        return (
          <button
            key={m.id}
            disabled={isLocked}
            title={isLocked ? "Najpierw zbuduj kontekst" : undefined}
            className={`
              relative px-4 py-1.5 rounded-lg text-sm font-medium
              transition-all duration-200
              ${isActive
                ? "bg-buddy-elevated text-buddy-gold-light shadow-sm"
                : isLocked
                  ? "text-buddy-text-ghost cursor-not-allowed"
                  : "text-buddy-text-muted hover:text-buddy-text hover:bg-buddy-elevated/50"
              }
            `}
          >
            {/* Desktop: full label */}
            <span className="hidden md:inline">{m.label}</span>
            {/* Mobile: short label */}
            <span className="md:hidden">{m.shortLabel}</span>

            {/* Active indicator dot — small gold dot below active tab */}
            {isActive && (
              <span className="absolute -bottom-0.5 left-1/2 -translate-x-1/2
                               w-1 h-1 rounded-full bg-buddy-gold" />
            )}

            {/* Lock icon for disabled tabs */}
            {isLocked && (
              <svg width="10" height="10" viewBox="0 0 10 10"
                fill="currentColor" className="inline ml-1 opacity-40">
                <path d="M3 4V3a2 2 0 114 0v1h1a1 1 0 011 1v3a1 1 0 01-1 1H2a1 1 0 01-1-1V5a1 1 0 011-1h1zm1 0h2V3a1 1 0 10-2 0v1z" />
              </svg>
            )}
          </button>
        );
      })}
    </div>
  );
}
