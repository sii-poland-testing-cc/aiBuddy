/**
 * MOCKUP: PanelCard
 *
 * Collapsible card wrapper for all side panel content.
 * Used inside SidePanel to wrap: MindMap, Glossary, HeatmapTable,
 * AuditFileSelector, AuditHistory, TierSelector, etc.
 *
 * Behavior:
 * - Click header to toggle open/close (200ms transition)
 * - Chevron rotates on toggle
 * - Optional badge (count) in header
 * - Content area has max-height with scroll
 * - Default open/close state per card (set by parent)
 *
 * Default states by mode:
 *   Context:      MindMap=open, Glossary=closed, Status=closed
 *   Requirements: Heatmap=open, Stats=open
 *   Analyzer:     Files=open, History=closed, Tier=closed
 */

interface PanelCardProps {
  title: string;
  icon?: React.ReactNode;
  defaultOpen?: boolean;
  badge?: string | number;
  children: React.ReactNode;
  maxHeight?: string; // default "400px", MindMap uses "50vh"
}

export default function PanelCardMockup() {
  // Showing two states: open and closed

  return (
    <div className="flex flex-col gap-2 p-3">

      {/* ─── OPEN CARD ─── */}
      <div className="border border-buddy-border rounded-lg overflow-hidden bg-buddy-surface">
        {/* Header — always visible, clickable */}
        <button className="w-full flex items-center gap-2 px-3 py-2.5
                           text-left hover:bg-buddy-elevated/50 transition-colors">
          {/* Optional icon */}
          <span className="text-buddy-text-dim shrink-0 w-4 h-4 flex items-center justify-center text-xs">
            🗺
          </span>
          {/* Title */}
          <span className="text-xs font-semibold text-buddy-text-muted flex-1">
            Mapa mysli
          </span>
          {/* Optional badge */}
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-buddy-elevated text-buddy-text-dim font-mono">
            12
          </span>
          {/* Chevron — rotated 180 when open */}
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
               className="text-buddy-text-faint rotate-180 transition-transform duration-200">
            <polyline points="3,5 6,8 9,5" />
          </svg>
        </button>
        {/* Content — scrollable within maxHeight */}
        <div className="border-t border-buddy-border overflow-y-auto" style={{ maxHeight: "400px" }}>
          <div className="p-3">
            <div className="h-[200px] bg-buddy-base rounded-lg border border-buddy-border flex items-center justify-center text-xs text-buddy-text-faint">
              [MindMap component renders here]
            </div>
          </div>
        </div>
      </div>

      {/* ─── CLOSED CARD ─── */}
      <div className="border border-buddy-border rounded-lg overflow-hidden bg-buddy-surface">
        <button className="w-full flex items-center gap-2 px-3 py-2.5
                           text-left hover:bg-buddy-elevated/50 transition-colors">
          <span className="text-buddy-text-dim shrink-0 w-4 h-4 flex items-center justify-center text-xs">
            📖
          </span>
          <span className="text-xs font-semibold text-buddy-text-muted flex-1">
            Glosariusz
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-buddy-elevated text-buddy-text-dim font-mono">
            24
          </span>
          {/* Chevron — pointing down when closed */}
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
               className="text-buddy-text-faint transition-transform duration-200">
            <polyline points="3,5 6,8 9,5" />
          </svg>
        </button>
        {/* No content section when closed */}
      </div>
    </div>
  );
}
