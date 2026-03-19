/**
 * MOCKUP: SidePanel
 *
 * Right-side container for mode-specific PanelCards.
 * Width: 360px on desktop. Hidden on mobile, overlay on tablet.
 *
 * Behavior:
 * - Toggleable via button in top-right header (or Cmd+.)
 * - Contains different PanelCard sets depending on active mode
 * - Scrollable if cards exceed viewport height
 * - Has subtle border-left separator from main content
 *
 * Contents by mode:
 *   Context:      [MindMap card] [Glossary card] [Status card] [Build mode card]
 *   Requirements: [Heatmap card] [Mapping card]
 *   Analyzer:     [File selector card] [Audit history card] [Tier selector card]
 */

export default function SidePanelMockup() {
  return (
    <aside className="w-[360px] border-l border-buddy-border
                      flex flex-col gap-2 p-3 overflow-y-auto
                      bg-buddy-base hidden lg:flex">

      {/* Example: Context mode cards */}

      {/* Card 1: Mind Map (open by default) */}
      <div className="border border-buddy-border rounded-lg overflow-hidden bg-buddy-surface">
        <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50 transition-colors">
          <span className="text-xs font-semibold text-buddy-text-muted flex-1">Mapa mysli</span>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
               className="text-buddy-text-faint rotate-180">
            <polyline points="3,5 6,8 9,5" />
          </svg>
        </button>
        <div className="border-t border-buddy-border p-3">
          <div className="h-[250px] bg-buddy-base rounded-lg border border-buddy-border flex items-center justify-center text-xs text-buddy-text-faint">
            [MindMap SVG]
          </div>
        </div>
      </div>

      {/* Card 2: Glossary (closed by default) */}
      <div className="border border-buddy-border rounded-lg overflow-hidden bg-buddy-surface">
        <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50 transition-colors">
          <span className="text-xs font-semibold text-buddy-text-muted flex-1">Glosariusz</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-buddy-elevated text-buddy-text-dim font-mono">24</span>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
               className="text-buddy-text-faint">
            <polyline points="3,5 6,8 9,5" />
          </svg>
        </button>
      </div>

      {/* Card 3: Context Status (closed by default) */}
      <div className="border border-buddy-border rounded-lg overflow-hidden bg-buddy-surface">
        <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50 transition-colors">
          <span className="text-xs font-semibold text-buddy-text-muted flex-1">Status kontekstu</span>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
               className="text-buddy-text-faint">
            <polyline points="3,5 6,8 9,5" />
          </svg>
        </button>
      </div>
    </aside>
  );
}
