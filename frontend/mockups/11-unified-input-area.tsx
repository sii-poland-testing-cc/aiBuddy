/**
 * MOCKUP: UnifiedInputArea
 *
 * Claude-style input with + attachment button.
 * Replaces: ChatInputArea.tsx + context page upload zone
 *
 * Behavior:
 * - + button (left) opens native file picker
 * - File accept types change per mode:
 *   - context: .docx,.pdf
 *   - requirements: .docx,.pdf
 *   - analyzer: .xlsx,.csv,.json,.pdf,.feature,.txt,.md
 * - Placeholder text changes per mode
 * - Attached files appear as FileChip components above the input
 * - Enter sends, Shift+Enter = new line
 * - Send button becomes Stop button when isLoading
 * - In context mode: attached files trigger context build, not chat upload
 */

import type { Mode } from "./10-mode-bar";

const PLACEHOLDER_MAP: Record<Mode, string> = {
  context: "Zapytaj o domene lub dolacz dokumenty...",
  requirements: "Zapytaj o wymagania...",
  analyzer: "Opisz co chcesz zaudytowac lub dolacz pliki testowe...",
};

export default function UnifiedInputAreaMockup({ mode = "context" as Mode }) {
  const hasAttachments = true; // mockup: show attachment state

  return (
    <div className="px-4 md:px-8 lg:px-0 pb-6 pt-3 shrink-0">
      <div className="max-w-[768px] mx-auto">

        {/* ─── Attached file chips (shown when files are pending) ─── */}
        {hasAttachments && (
          <div className="flex flex-wrap gap-1.5 mb-2">
            {/* FileChip components — see 16-file-chip.tsx */}
            <div className="inline-flex items-center gap-1.5 bg-buddy-elevated border border-buddy-border rounded-lg px-2.5 py-1 text-xs">
              <span className="font-mono text-buddy-gold/70 text-[10px]">DOCX</span>
              <span className="text-buddy-text max-w-[140px] truncate">srs_payment.docx</span>
              <button className="text-buddy-text-dim hover:text-buddy-gold transition-colors ml-0.5">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <line x1="3" y1="3" x2="9" y2="9" /><line x1="9" y1="3" x2="3" y2="9" />
                </svg>
              </button>
            </div>
            <div className="inline-flex items-center gap-1.5 bg-buddy-elevated border border-buddy-border rounded-lg px-2.5 py-1 text-xs">
              <span className="font-mono text-buddy-gold/70 text-[10px]">PDF</span>
              <span className="text-buddy-text max-w-[140px] truncate">test_plan.pdf</span>
              <button className="text-buddy-text-dim hover:text-buddy-gold transition-colors ml-0.5">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <line x1="3" y1="3" x2="9" y2="9" /><line x1="9" y1="3" x2="3" y2="9" />
                </svg>
              </button>
            </div>
          </div>
        )}

        {/* ─── Input container — rounded box with + and send buttons ─── */}
        <div className="relative flex items-end gap-2
                        bg-buddy-surface border border-buddy-border-dark
                        rounded-xl px-3 py-2.5
                        focus-within:border-buddy-gold/50
                        transition-colors">

          {/* + Attachment button (like Claude Desktop) */}
          <button
            className="w-8 h-8 rounded-lg flex items-center justify-center
                       text-buddy-text-dim hover:text-buddy-text
                       hover:bg-buddy-elevated transition-colors
                       shrink-0 mb-0.5"
            title="Dolacz pliki"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none"
                 stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <line x1="9" y1="4" x2="9" y2="14" />
              <line x1="4" y1="9" x2="14" y2="9" />
            </svg>
          </button>

          {/* Textarea — auto-growing, max 140px height */}
          <textarea
            placeholder={PLACEHOLDER_MAP[mode]}
            rows={1}
            className="flex-1 bg-transparent text-sm text-buddy-text
                       placeholder:text-buddy-text-faint leading-relaxed
                       max-h-[140px] overflow-y-auto py-1.5
                       focus:outline-none"
          />

          {/* Send button — gold gradient when can send, gray when empty */}
          {/* Becomes stop button (square icon) when isLoading */}
          <button
            className="w-8 h-8 rounded-lg flex items-center justify-center
                       shrink-0 mb-0.5 transition-all
                       bg-gradient-to-br from-buddy-gold to-buddy-gold-light
                       text-buddy-surface hover:opacity-90"
          >
            {/* Send arrow icon */}
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"
                 stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="7" y1="11" x2="7" y2="3" />
              <polyline points="3,7 7,3 11,7" />
            </svg>
          </button>
        </div>

        {/* ─── Hint text ─── */}
        <p className="text-center mt-2 text-[11px] text-buddy-text-ghost">
          Enter &mdash; wyslij &middot; Shift+Enter &mdash; nowa linia
        </p>
      </div>
    </div>
  );
}
