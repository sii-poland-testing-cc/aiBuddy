/**
 * MOCKUP: FileChip
 *
 * Small badge for attached files, shown above the input area.
 * Shows file extension + filename + remove button.
 *
 * Behavior:
 * - Truncated at 140px
 * - X button removes the file from pending list
 * - Extension shown in gold mono font
 */

export default function FileChipMockup() {
  return (
    <div className="flex gap-1.5">
      {/* Chip 1 */}
      <div className="inline-flex items-center gap-1.5 bg-buddy-elevated border border-buddy-border rounded-lg px-2.5 py-1 text-xs">
        <span className="font-mono text-buddy-gold/70 text-[10px]">DOCX</span>
        <span className="text-buddy-text max-w-[140px] truncate">srs_payment_module.docx</span>
        <button className="text-buddy-text-dim hover:text-buddy-gold transition-colors ml-0.5">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <line x1="3" y1="3" x2="9" y2="9" />
            <line x1="9" y1="3" x2="3" y2="9" />
          </svg>
        </button>
      </div>

      {/* Chip 2 */}
      <div className="inline-flex items-center gap-1.5 bg-buddy-elevated border border-buddy-border rounded-lg px-2.5 py-1 text-xs">
        <span className="font-mono text-buddy-gold/70 text-[10px]">PDF</span>
        <span className="text-buddy-text max-w-[140px] truncate">test_plan.pdf</span>
        <button className="text-buddy-text-dim hover:text-buddy-gold transition-colors ml-0.5">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <line x1="3" y1="3" x2="9" y2="9" />
            <line x1="9" y1="3" x2="3" y2="9" />
          </svg>
        </button>
      </div>
    </div>
  );
}
