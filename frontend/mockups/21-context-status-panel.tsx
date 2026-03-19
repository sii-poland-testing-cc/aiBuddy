/**
 * MOCKUP: ContextStatusPanel
 *
 * Small widget in the side panel (Context mode) showing:
 * - Build timestamp
 * - Entity/term counts
 * - List of indexed documents
 * - Build progress (when building)
 *
 * Also includes "Przebuduj kontekst" button to trigger rebuild.
 */

export default function ContextStatusPanelMockup() {
  return (
    <div className="flex flex-col gap-3">

      {/* ─── Status: context built ─── */}
      <div className="space-y-2">
        <div className="text-[10px] text-emerald-400">
          Kontekst zbudowany: 19 mar 2026, 14:32
        </div>
        <div className="flex gap-2 text-[10px]">
          <span className="px-2 py-0.5 rounded bg-buddy-gold/10 text-buddy-gold border border-buddy-gold/20 font-mono">
            12 encji
          </span>
          <span className="px-2 py-0.5 rounded bg-buddy-border text-buddy-text-muted border border-buddy-border-dark font-mono">
            24 terminow
          </span>
        </div>
        <div className="space-y-1">
          <div className="text-[10px] text-buddy-text-faint font-semibold">Zaindeksowane dokumenty:</div>
          <div className="text-[10px] text-buddy-text-muted font-mono truncate">srs_payment_module.docx</div>
          <div className="text-[10px] text-buddy-text-muted font-mono truncate">test_plan_payment.docx</div>
          <div className="text-[10px] text-buddy-text-muted font-mono truncate">qa_process.docx</div>
        </div>
      </div>

      {/* ─── Status: building (alternative state) ─── */}
      {false && (
        <div className="space-y-2">
          <div className="flex gap-1">
            {["Parsowanie", "Indeksowanie", "Ekstrakcja", "Asemblacja"].map((s, i) => (
              <div key={s} className={`flex-1 py-1 rounded text-center text-[10px] font-semibold transition-all ${
                i <= 1 ? "bg-buddy-gold/15 text-buddy-gold border border-buddy-gold/30"
                       : "bg-buddy-base text-buddy-text-ghost border border-buddy-border"
              }`}>
                {s}
              </div>
            ))}
          </div>
          <div className="text-xs text-buddy-gold">Budowanie indeksu RAG...</div>
          <div className="h-1 bg-buddy-border rounded-sm overflow-hidden">
            <div className="h-full bg-buddy-gold rounded-sm" style={{ width: "45%" }} />
          </div>
        </div>
      )}
    </div>
  );
}
