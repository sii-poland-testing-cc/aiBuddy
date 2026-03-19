/**
 * MOCKUP: RequirementsView
 *
 * Inline view for requirements registry (rendered in the center content area
 * when mode="requirements"). Replaces the separate /requirements/[projectId] page.
 *
 * Behavior:
 * - Scrollable list of requirement cards grouped by module
 * - Search/filter bar at top
 * - "Wyodrebnij wymagania" button in header
 * - Extraction progress inline
 * - Collapsible module groups
 * - Each RequirementCard shows: external_id, title, description, level badge,
 *   source_type badge, confidence %, review status, mark-reviewed button
 * - Centered at max-width 768px
 *
 * Note: Heatmap + Mapping controls move to the SidePanel (PanelCards)
 */

export default function RequirementsViewMockup() {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-[768px] mx-auto px-6 py-6">

        {/* ─── Header ─── */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-buddy-text">Rejestr wymagan</h2>
            <p className="text-xs text-buddy-text-muted mt-0.5">
              42 wymagan / 3 do przegladu
            </p>
          </div>
          <button className="px-4 py-2 bg-gradient-to-r from-buddy-gold to-buddy-gold-light
                             text-buddy-surface text-sm font-medium rounded-lg
                             hover:opacity-90 disabled:opacity-40 transition-all">
            Wyodrebnij ponownie
          </button>
        </div>

        {/* ─── Search ─── */}
        <input
          placeholder="Filtruj wymagania..."
          className="w-full bg-buddy-elevated border border-buddy-border-dark
                     rounded-xl px-4 py-3 text-sm text-buddy-text
                     placeholder:text-buddy-text-faint mb-4
                     focus:outline-none focus:border-buddy-gold"
        />

        {/* ─── Module group (open) ─── */}
        <div className="flex flex-col gap-3">
          <div className="border border-buddy-border rounded-xl overflow-hidden bg-buddy-surface">
            <button className="w-full flex items-center gap-2 px-4 py-2.5 text-left
                               hover:bg-buddy-elevated/50 transition-colors">
              <span className="text-xs font-semibold text-buddy-text-muted font-mono">Payment</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-buddy-border text-buddy-text-dim font-mono">8</span>
              <span className="ml-auto text-[10px] text-buddy-text-faint">▲</span>
            </button>
            <div className="border-t border-buddy-border p-3 flex flex-col gap-2">

              {/* RequirementCard example */}
              <div className="rounded-lg bg-buddy-elevated p-3 border border-buddy-border">
                <div className="flex items-start gap-2">
                  <span className="shrink-0 font-mono text-[10px] px-1.5 py-0.5 rounded border
                                   bg-buddy-border text-buddy-text-dim border-buddy-border-dark">
                    FR-001
                  </span>
                  <span className="flex-1 text-sm font-medium text-buddy-text leading-snug">
                    System powinien przetwarzac platnosci kartowe w czasie rzeczywistym
                  </span>
                  <span className="shrink-0 text-[10px] font-mono text-buddy-text-muted">87%</span>
                </div>
                <p className="mt-1.5 text-xs text-buddy-text-muted leading-relaxed line-clamp-2">
                  Platnosci kartowe (Visa, Mastercard) powinny byc przetwarzane w ciagu 3 sekund od momentu autoryzacji.
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] px-1.5 py-0.5 rounded border font-medium
                                   bg-amber-500/20 text-amber-300 border-amber-500/30">
                    functional req
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded border
                                   bg-blue-500/10 text-blue-400 border-blue-500/20">
                    explicit
                  </span>
                  <div className="ml-auto">
                    <button className="text-[10px] px-2 py-0.5 rounded border border-emerald-500/30
                                       bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20
                                       transition-colors">
                      ✓ Oznacz
                    </button>
                  </div>
                </div>
              </div>

              {/* RequirementCard with needs_review flag */}
              <div className="rounded-lg bg-buddy-elevated p-3 border border-buddy-border border-l-4 border-l-amber-500">
                <div className="flex items-start gap-2">
                  <span className="shrink-0 font-mono text-[10px] px-1.5 py-0.5 rounded border
                                   bg-buddy-border text-buddy-text-dim border-buddy-border-dark">
                    FR-005
                  </span>
                  <span className="flex-1 text-sm font-medium text-buddy-text leading-snug">
                    Zwroty powinny byc procesowane automatycznie
                  </span>
                  <span className="shrink-0 text-[10px] font-mono text-buddy-text-muted">52%</span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] px-1.5 py-0.5 rounded border font-medium
                                   bg-amber-500/20 text-amber-300 border-amber-500/30">
                    functional req
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-400/40
                                   bg-amber-400/10 text-amber-400 font-medium">
                    do przegladu
                  </span>
                  <div className="ml-auto">
                    <button className="text-[10px] px-2 py-0.5 rounded border border-emerald-500/30
                                       bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20
                                       transition-colors">
                      ✓ Oznacz
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Module group (collapsed) */}
          <div className="border border-buddy-border rounded-xl overflow-hidden bg-buddy-surface">
            <button className="w-full flex items-center gap-2 px-4 py-2.5 text-left
                               hover:bg-buddy-elevated/50 transition-colors">
              <span className="text-xs font-semibold text-buddy-text-muted font-mono">Authentication</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-buddy-border text-buddy-text-dim font-mono">5</span>
              <span className="ml-auto text-[10px] text-buddy-text-faint">▼</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
