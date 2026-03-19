/**
 * MOCKUP: Unified Project Page (/project/[projectId])
 *
 * This is the CORE REDESIGN. One page replaces three:
 *   /context/[projectId]      → mode="context"
 *   /requirements/[projectId] → mode="requirements"
 *   /chat/[projectId]         → mode="analyzer"
 *
 * Layout:
 * ┌──────────────────────────────────────────────────────────┐
 * │ [ProjectSwitcher]  [Context|Reqs|Analyzer]  [RAG] [═]   │  ← header
 * ├──────────────────────────────────────────────────────────┤
 * │ [ProgressBar]                                            │  ← conditional
 * ├────────────────────────────────┬─────────────────────────┤
 * │                                │                         │
 * │   Center content (flex-1)      │  SidePanel (360px)      │
 * │   max-w: 768px, centered       │  PanelCards stacked     │
 * │                                │                         │
 * │   [MessageList / ReqsView]     │  [Card 1    ▼]          │
 * │                                │  [Card 2    ▼]          │
 * │                                │  [Card 3    ▼]          │
 * │                                │                         │
 * │   [UnifiedInputArea]           │                         │
 * └────────────────────────────────┴─────────────────────────┘
 *
 * State preserved across mode switches:
 * - Chat history (per mode)
 * - Uploaded files
 * - Panel open/close states
 * - Selected audit files
 *
 * Hooks used (UNCHANGED from current codebase):
 * - useContextBuilder(projectId)
 * - useAIBuddyChat({ projectId, tier })
 * - useProjectFiles(projectId)
 * - useRequirements(projectId)
 * - useHeatmap(projectId)
 *
 * What gets REMOVED from current codebase:
 * - Sidebar.tsx (replaced by ProjectSwitcher + ModeBar)
 * - PipelineSteps.tsx (replaced by TierSelector in side panel)
 * - ChatInputArea.tsx (replaced by UnifiedInputArea)
 * - /context/[projectId]/page.tsx
 * - /chat/[projectId]/page.tsx
 * - /requirements/[projectId]/page.tsx
 */

export default function UnifiedProjectPageMockup() {
  // Mock state
  const mode = "context"; // "context" | "requirements" | "analyzer"
  const contextReady = true;
  const sidePanelOpen = true;

  return (
    <div className="flex flex-col h-screen bg-buddy-base text-buddy-text font-sans">

      {/* ═══════════════════════════════════════════════════════
          HEADER BAR
          ═══════════════════════════════════════════════════════ */}
      <header className="flex items-center px-4 py-3 border-b border-buddy-border bg-buddy-surface shrink-0">

        {/* LEFT: Project Switcher — see 14-project-switcher.tsx */}
        <div className="shrink-0 flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-buddy-elevated">
          <div className="w-6 h-6 rounded-md bg-gradient-to-br from-buddy-gold to-buddy-gold-light
                          flex items-center justify-center text-[10px] font-bold text-buddy-surface">Q</div>
          <span className="text-sm font-medium text-buddy-text">PayFlow Module</span>
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5"
               className="text-buddy-text-faint"><polyline points="2,4 5,7 8,4" /></svg>
        </div>

        {/* CENTER: Mode Bar — see 10-mode-bar.tsx */}
        <div className="flex-1 flex justify-center">
          <div className="flex items-center bg-buddy-surface border border-buddy-border rounded-xl p-1 gap-0.5">
            {/* Active tab */}
            <button className="relative px-4 py-1.5 rounded-lg text-sm font-medium bg-buddy-elevated text-buddy-gold-light shadow-sm">
              Context Builder
              <span className="absolute -bottom-0.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-buddy-gold" />
            </button>
            {/* Inactive tab */}
            <button className="px-4 py-1.5 rounded-lg text-sm font-medium text-buddy-text-muted hover:text-buddy-text hover:bg-buddy-elevated/50 transition-all">
              Requirements
            </button>
            {/* Inactive tab */}
            <button className="px-4 py-1.5 rounded-lg text-sm font-medium text-buddy-text-muted hover:text-buddy-text hover:bg-buddy-elevated/50 transition-all">
              Suite Analyzer
            </button>
          </div>
        </div>

        {/* RIGHT: Status + Panel toggle */}
        <div className="flex items-center gap-2 shrink-0">
          {/* RAG badge (when context is ready) */}
          <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-emerald-400/10 text-emerald-400 border border-emerald-400/20">
            RAG
          </span>

          {/* Side panel toggle */}
          <button className="p-2 rounded-lg text-buddy-text-dim hover:text-buddy-text hover:bg-buddy-elevated transition-colors"
                  title="Ukryj panel">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="1" y="2" width="16" height="14" rx="2" />
              <line x1="11" y1="2" x2="11" y2="16" />
            </svg>
          </button>
        </div>
      </header>

      {/* ═══════════════════════════════════════════════════════
          PROGRESS BAR (conditional) — see 15-progress-bar.tsx
          ═══════════════════════════════════════════════════════ */}
      {false && (
        <div className="px-6 py-2 border-b border-buddy-border shrink-0">
          <div className="max-w-[768px] mx-auto">
            <div className="flex justify-between text-xs mb-1">
              <span className="text-buddy-gold">Budowanie indeksu RAG...</span>
              <span className="text-buddy-text-faint font-mono">45%</span>
            </div>
            <div className="w-full h-0.5 bg-buddy-border rounded-full overflow-hidden">
              <div className="h-full bg-buddy-gold rounded-full" style={{ width: "45%" }} />
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════
          MAIN CONTENT AREA
          ═══════════════════════════════════════════════════════ */}
      <div className="flex-1 flex overflow-hidden">

        {/* ─── CENTER: Conversation / Content ─── */}
        <div className="flex-1 flex flex-col min-w-0">

          {/* CENTER CONTENT — depends on mode */}
          {mode === "context" && contextReady && (
            /* Context mode with RAG chat: MessageList */
            <div className="flex-1 overflow-y-auto px-6 py-6">
              <div className="max-w-[768px] mx-auto space-y-4">

                {/* Assistant message — NO background card (Claude-style) */}
                <div className="flex justify-start">
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-buddy-gold to-buddy-gold-light
                                  flex items-center justify-center text-xs font-bold text-buddy-surface shrink-0 mt-1 mr-3">Q</div>
                  <div className="max-w-[80%] text-sm leading-relaxed text-buddy-text py-1">
                    Baza wiedzy gotowa. Zapytaj o cokolwiek dotyczacego domeny.
                  </div>
                </div>

                {/* User message — subtle accent tint background */}
                <div className="flex justify-end">
                  <div className="max-w-[80%] text-sm leading-relaxed bg-buddy-gold/15 text-buddy-text
                                  rounded-2xl rounded-br-md px-4 py-3">
                    Wyjasn termin: &quot;autoryzacja platnosci&quot;
                  </div>
                </div>

                {/* Assistant reply */}
                <div className="flex justify-start">
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-buddy-gold to-buddy-gold-light
                                  flex items-center justify-center text-xs font-bold text-buddy-surface shrink-0 mt-1 mr-3">Q</div>
                  <div className="max-w-[80%] text-sm leading-relaxed text-buddy-text py-1">
                    <strong className="font-semibold text-buddy-gold-light">Opis</strong><br/>
                    Autoryzacja platnosci to proces weryfikacji...<br/><br/>
                    <strong className="font-semibold text-buddy-gold-light">Kontekst</strong><br/>
                    W systemie PayFlow autoryzacja odbywa sie...<br/><br/>
                    <strong className="font-semibold text-buddy-gold-light">Powiazane terminy</strong> —{" "}
                    <span className="text-buddy-gold-light font-semibold cursor-pointer" style={{ borderBottom: "1px dashed #c8902a" }}>
                      tokenizacja
                    </span>{" "}
                    <span className="text-buddy-gold-light font-semibold cursor-pointer" style={{ borderBottom: "1px dashed #c8902a" }}>
                      3D Secure
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {mode === "context" && !contextReady && (
            /* Context mode, no context yet: empty state */
            <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-6">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-buddy-gold to-buddy-gold-light
                              flex items-center justify-center text-2xl font-bold text-buddy-surface">Q</div>
              <div>
                <h2 className="text-lg font-semibold text-buddy-text mb-1">Context Builder</h2>
                <p className="text-sm text-buddy-text-muted max-w-md">
                  Przeslij dokumentacje projektu (.docx, .pdf) za pomoca przycisku + ponizej,
                  aby zbudowac baze wiedzy RAG.
                </p>
              </div>
            </div>
          )}

          {mode === "requirements" && (
            /* Requirements mode: scrollable registry — see 20-requirements-view.tsx */
            <div className="flex-1 overflow-y-auto">
              <div className="max-w-[768px] mx-auto px-6 py-6 text-xs text-buddy-text-faint text-center">
                [RequirementsView renders here — see 20-requirements-view.tsx]
              </div>
            </div>
          )}

          {mode === "analyzer" && (
            /* Analyzer mode: audit chat — same MessageList */
            <div className="flex-1 overflow-y-auto px-6 py-6">
              <div className="max-w-[768px] mx-auto text-xs text-buddy-text-faint text-center">
                [Audit chat MessageList renders here]
              </div>
            </div>
          )}

          {/* ─── INPUT AREA (not shown for requirements mode) ─── */}
          {mode !== "requirements" && (
            /* UnifiedInputArea — see 11-unified-input-area.tsx */
            <div className="px-4 md:px-8 lg:px-0 pb-6 pt-3 shrink-0">
              <div className="max-w-[768px] mx-auto">
                <div className="relative flex items-end gap-2 bg-buddy-surface border border-buddy-border-dark
                                rounded-xl px-3 py-2.5 focus-within:border-buddy-gold/50 transition-colors">
                  {/* + button */}
                  <button className="w-8 h-8 rounded-lg flex items-center justify-center text-buddy-text-dim hover:text-buddy-text hover:bg-buddy-elevated transition-colors shrink-0 mb-0.5">
                    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                      <line x1="9" y1="4" x2="9" y2="14" /><line x1="4" y1="9" x2="14" y2="9" />
                    </svg>
                  </button>
                  {/* Textarea */}
                  <textarea placeholder="Zapytaj o domene lub dolacz dokumenty..." rows={1}
                    className="flex-1 bg-transparent text-sm text-buddy-text placeholder:text-buddy-text-faint leading-relaxed py-1.5 focus:outline-none" />
                  {/* Send */}
                  <button className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mb-0.5 bg-buddy-elevated text-buddy-text-ghost">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <line x1="7" y1="11" x2="7" y2="3" /><polyline points="3,7 7,3 11,7" />
                    </svg>
                  </button>
                </div>
                <p className="text-center mt-2 text-[11px] text-buddy-text-ghost">
                  Enter &mdash; wyslij &middot; Shift+Enter &mdash; nowa linia
                </p>
              </div>
            </div>
          )}
        </div>

        {/* ─── RIGHT: Side Panel (360px, toggleable) ─── */}
        {/* See 13-side-panel.tsx for structure */}
        {sidePanelOpen && (
          <aside className="w-[360px] border-l border-buddy-border flex flex-col gap-2 p-3 overflow-y-auto bg-buddy-base hidden lg:flex">

            {mode === "context" && (
              <>
                {/* Card: Mind Map (open) */}
                <div className="border border-buddy-border rounded-lg overflow-hidden bg-buddy-surface">
                  <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50">
                    <span className="text-xs font-semibold text-buddy-text-muted flex-1">Mapa mysli</span>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
                         className="text-buddy-text-faint rotate-180"><polyline points="3,5 6,8 9,5" /></svg>
                  </button>
                  <div className="border-t border-buddy-border p-3" style={{ maxHeight: "50vh" }}>
                    <div className="h-[250px] bg-buddy-base rounded-lg border border-buddy-border flex items-center justify-center text-xs text-buddy-text-faint">
                      [MindMap SVG — dagre layout, same component]
                    </div>
                  </div>
                </div>

                {/* Card: Glossary (closed) */}
                <div className="border border-buddy-border rounded-lg bg-buddy-surface">
                  <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50">
                    <span className="text-xs font-semibold text-buddy-text-muted flex-1">Glosariusz</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-buddy-elevated text-buddy-text-dim font-mono">24</span>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
                         className="text-buddy-text-faint"><polyline points="3,5 6,8 9,5" /></svg>
                  </button>
                </div>

                {/* Card: Context Status (closed) */}
                <div className="border border-buddy-border rounded-lg bg-buddy-surface">
                  <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50">
                    <span className="text-xs font-semibold text-buddy-text-muted flex-1">Status kontekstu</span>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
                         className="text-buddy-text-faint"><polyline points="3,5 6,8 9,5" /></svg>
                  </button>
                </div>

                {/* Card: Build mode (closed) */}
                <div className="border border-buddy-border rounded-lg bg-buddy-surface">
                  <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50">
                    <span className="text-xs font-semibold text-buddy-text-muted flex-1">Tryb budowania</span>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
                         className="text-buddy-text-faint"><polyline points="3,5 6,8 9,5" /></svg>
                  </button>
                </div>
              </>
            )}

            {mode === "requirements" && (
              <>
                {/* Card: Heatmap (open) — see 23-heatmap-table.tsx */}
                <div className="border border-buddy-border rounded-lg overflow-hidden bg-buddy-surface">
                  <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50">
                    <span className="text-xs font-semibold text-buddy-text-muted flex-1">Heatmapa pokrycia</span>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
                         className="text-buddy-text-faint rotate-180"><polyline points="3,5 6,8 9,5" /></svg>
                  </button>
                  <div className="border-t border-buddy-border p-3 text-xs text-buddy-text-faint">
                    [HeatmapTable — see 23-heatmap-table.tsx]
                  </div>
                </div>

                {/* Card: Mapping controls (open) */}
                <div className="border border-buddy-border rounded-lg overflow-hidden bg-buddy-surface">
                  <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50">
                    <span className="text-xs font-semibold text-buddy-text-muted flex-1">Mapowanie</span>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
                         className="text-buddy-text-faint rotate-180"><polyline points="3,5 6,8 9,5" /></svg>
                  </button>
                  <div className="border-t border-buddy-border p-3">
                    <button className="w-full px-3 py-2 bg-buddy-elevated border border-buddy-border-dark
                                       text-xs text-buddy-text-muted rounded-lg
                                       hover:border-buddy-gold hover:text-buddy-gold-light transition-all">
                      Uruchom mapowanie
                    </button>
                  </div>
                </div>
              </>
            )}

            {mode === "analyzer" && (
              <>
                {/* Card: File selector (open) */}
                <div className="border border-buddy-border rounded-lg overflow-hidden bg-buddy-surface">
                  <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50">
                    <span className="text-xs font-semibold text-buddy-text-muted flex-1">Pliki do audytu</span>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
                         className="text-buddy-text-faint rotate-180"><polyline points="3,5 6,8 9,5" /></svg>
                  </button>
                  <div className="border-t border-buddy-border p-3 text-xs text-buddy-text-faint">
                    [AuditFileSelector — existing component, compact mode]
                  </div>
                </div>

                {/* Card: Audit History (closed) */}
                <div className="border border-buddy-border rounded-lg bg-buddy-surface">
                  <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50">
                    <span className="text-xs font-semibold text-buddy-text-muted flex-1">Historia audytow</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-buddy-elevated text-buddy-text-dim font-mono">3</span>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
                         className="text-buddy-text-faint"><polyline points="3,5 6,8 9,5" /></svg>
                  </button>
                </div>

                {/* Card: Tier selector (closed) — see 22-tier-selector.tsx */}
                <div className="border border-buddy-border rounded-lg bg-buddy-surface">
                  <button className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-buddy-elevated/50">
                    <span className="text-xs font-semibold text-buddy-text-muted flex-1">Tryb analizy</span>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"
                         className="text-buddy-text-faint"><polyline points="3,5 6,8 9,5" /></svg>
                  </button>
                </div>
              </>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
