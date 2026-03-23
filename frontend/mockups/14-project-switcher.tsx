/**
 * MOCKUP: ProjectSwitcher
 *
 * Minimal dropdown in top-left of the header.
 * Replaces: Full sidebar project list + logo + tabs
 *
 * Behavior:
 * - Shows current project name with Q logo mark
 * - Click opens dropdown with all projects
 * - Each project row shows context-ready dot (green/gray)
 * - Active project has checkmark
 * - "Nowy projekt" inline create at bottom
 * - "Wszystkie projekty" link to home page
 * - Dropdown closes on outside click
 */

export default function ProjectSwitcherMockup() {
  const isOpen = true; // mockup: showing open state

  return (
    <div className="relative">

      {/* ─── Trigger button ─── */}
      <button className="flex items-center gap-2 px-3 py-1.5
                         rounded-lg hover:bg-buddy-elevated transition-colors">
        {/* Logo mark */}
        <div className="w-6 h-6 rounded-md bg-gradient-to-br from-buddy-gold to-buddy-gold-light
                        flex items-center justify-center text-[10px] font-bold text-buddy-surface">
          Q
        </div>
        {/* Current project name */}
        <span className="text-sm font-medium text-buddy-text max-w-[160px] truncate">
          PayFlow Module
        </span>
        {/* Chevron */}
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5"
             className="text-buddy-text-faint">
          <polyline points="2,4 5,7 8,4" />
        </svg>
      </button>

      {/* ─── Dropdown (shown when open) ─── */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-1 z-50
                        w-64 bg-buddy-surface border border-buddy-border
                        rounded-xl shadow-lg overflow-hidden">

          {/* Project list */}
          <div className="max-h-[280px] overflow-y-auto py-1">
            {/* Active project */}
            <button className="w-full text-left px-3 py-2 bg-buddy-elevated
                               flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-buddy-success shrink-0" />
              <span className="text-sm text-buddy-text truncate flex-1">PayFlow Module</span>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"
                   className="text-buddy-gold shrink-0">
                <path d="M2 6l3 3 5-5" />
              </svg>
            </button>

            {/* Other project */}
            <button className="w-full text-left px-3 py-2 hover:bg-buddy-elevated
                               transition-colors flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-buddy-border-dark shrink-0" />
              <span className="text-sm text-buddy-text truncate flex-1">Auth Service</span>
            </button>
          </div>

          {/* New project */}
          <div className="border-t border-buddy-border p-2">
            <button className="w-full text-left px-3 py-2 rounded-lg text-sm text-buddy-text-muted
                               hover:bg-buddy-elevated hover:text-buddy-gold transition-colors
                               flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
                <line x1="7" y1="3" x2="7" y2="11" />
                <line x1="3" y1="7" x2="11" y2="7" />
              </svg>
              Nowy projekt
            </button>
          </div>

          {/* Home link */}
          <div className="border-t border-buddy-border p-2">
            <button className="w-full text-left px-3 py-1.5 rounded-lg text-xs text-buddy-text-faint
                               hover:text-buddy-text-muted transition-colors">
              Wszystkie projekty &rarr;
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
