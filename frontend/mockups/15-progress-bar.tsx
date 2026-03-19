/**
 * MOCKUP: ProgressBar
 *
 * Shared thin progress indicator shown below the header.
 * Used by all modes: context build, requirements extraction, mapping, audit.
 *
 * Behavior:
 * - Shows message on left, percentage on right
 * - Thin 0.5px gold bar fills proportionally
 * - Centered at max-width 768px (same as content)
 * - Only visible when a process is running
 */

export default function ProgressBarMockup() {
  return (
    <div className="px-6 py-2 border-b border-buddy-border shrink-0">
      <div className="max-w-[768px] mx-auto">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-buddy-gold">Analizowanie duplikatow...</span>
          <span className="text-buddy-text-faint font-mono">65%</span>
        </div>
        <div className="w-full h-0.5 bg-buddy-border rounded-full overflow-hidden">
          <div
            className="h-full bg-buddy-gold rounded-full transition-all duration-300 ease-out"
            style={{ width: "65%" }}
          />
        </div>
      </div>
    </div>
  );
}
