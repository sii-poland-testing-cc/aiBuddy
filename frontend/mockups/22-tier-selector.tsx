/**
 * MOCKUP: TierSelector
 *
 * Vertical list of analysis tiers for the Suite Analyzer side panel.
 * Replaces: PipelineSteps component (horizontal arrows)
 *
 * Tiers:
 * - Audyt (default active)
 * - Optymalizacja
 * - Regeneracja (locked — not yet implemented)
 */

export default function TierSelectorMockup() {
  return (
    <div className="flex flex-col gap-1">
      {/* Active tier */}
      <button className="px-3 py-2 rounded-lg text-xs text-left
                         bg-buddy-gold/15 border border-buddy-gold text-buddy-gold-light font-medium">
        Audyt
      </button>

      {/* Inactive tier */}
      <button className="px-3 py-2 rounded-lg text-xs text-left
                         border border-buddy-border text-buddy-text-muted
                         hover:border-buddy-muted hover:text-buddy-text transition-all">
        Optymalizacja
      </button>

      {/* Locked tier */}
      <button disabled className="px-3 py-2 rounded-lg text-xs text-left
                                  opacity-40 cursor-not-allowed text-buddy-text-faint
                                  border border-buddy-border">
        Regeneracja (wkrotce)
      </button>
    </div>
  );
}
