/**
 * MOCKUP: Home Page (/)
 *
 * Simplified Claude-style project selector.
 * Changes from current:
 * - Removed description field from create form
 * - Project rows are full-width clickable buttons (no separate "Otworz" button)
 * - Hover shows arrow indicator
 * - Context-ready dot indicator per project
 * - Routes to /project/[id] instead of /context/[id]
 * - "+ Nowy projekt" as dashed button below list
 */

// ─── MOCKUP ONLY — not wired to real hooks ──────────────────────────────────

export default function HomePageMockup() {
  // In real implementation: const { projects, createProject } = useProjects();
  const projects = [
    { project_id: "payflow", name: "PayFlow Module", created_at: "2026-03-15T10:00:00Z", hasContext: true },
    { project_id: "auth-service", name: "Auth Service", created_at: "2026-03-10T14:00:00Z", hasContext: false },
  ];
  const creating = false;

  return (
    <main className="flex min-h-screen items-center justify-center bg-buddy-base p-8">
      <div className="w-full max-w-md px-6">

        {/* ─── Logo — centered, minimal ─── */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl
                          bg-gradient-to-br from-buddy-gold to-buddy-gold-light
                          text-xl font-bold text-buddy-surface mb-4">
            Q
          </div>
          <h1 className="text-xl font-semibold text-buddy-text">AI Buddy</h1>
          <p className="text-sm text-buddy-text-muted mt-1">QA Agent Platform</p>
        </div>

        {/* ─── Project list — clean, no border cards ─── */}
        <div className="space-y-1 mb-6">
          {projects.map((p) => (
            <button
              key={p.project_id}
              // onClick={() => router.push(`/project/${p.project_id}`)}
              className="w-full flex items-center gap-3 px-4 py-3
                         rounded-lg hover:bg-buddy-elevated
                         transition-colors text-left group"
            >
              {/* Context ready indicator: green dot = context built, gray = not */}
              <div className={`w-2 h-2 rounded-full shrink-0 ${
                p.hasContext ? "bg-buddy-success" : "bg-buddy-border-dark"
              }`} />

              <div className="flex-1 min-w-0">
                <span className="text-sm font-medium text-buddy-text
                                 group-hover:text-buddy-gold-light transition-colors">
                  {p.name}
                </span>
                <span className="block text-xs text-buddy-text-dim mt-0.5">
                  {/* formatDate(p.created_at) */}
                  15 mar 2026
                </span>
              </div>

              {/* Arrow on hover */}
              <span className="text-buddy-text-faint opacity-0
                               group-hover:opacity-100 transition-opacity">
                &rarr;
              </span>
            </button>
          ))}
        </div>

        {/* ─── New project — inline input or dashed button ─── */}
        {creating ? (
          <form className="flex gap-2">
            <input
              autoFocus
              placeholder="Nazwa projektu..."
              className="flex-1 bg-buddy-elevated border border-buddy-border-dark
                         rounded-xl px-4 py-3 text-sm text-buddy-text
                         placeholder:text-buddy-text-faint
                         focus:outline-none focus:border-buddy-gold"
            />
            <button
              type="submit"
              className="px-4 py-3 bg-buddy-gold text-buddy-surface
                         rounded-xl text-sm font-medium
                         hover:bg-buddy-gold-light disabled:opacity-40
                         transition-all"
            >
              Utworz
            </button>
          </form>
        ) : (
          <button
            // onClick={() => setCreating(true)}
            className="w-full py-3 text-sm text-buddy-text-muted
                       hover:text-buddy-gold-light border border-dashed
                       border-buddy-border-dark rounded-xl
                       hover:border-buddy-gold transition-all"
          >
            + Nowy projekt
          </button>
        )}
      </div>
    </main>
  );
}
