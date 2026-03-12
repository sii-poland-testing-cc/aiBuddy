"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useProjectFiles } from "@/lib/useProjectFiles";
import { useContextBuilder } from "@/lib/useContextBuilder";
import { useRequirements, type Requirement } from "@/lib/useRequirements";
import { useHeatmap } from "@/lib/useHeatmap";
import Sidebar from "@/components/Sidebar";

// ── Helpers ───────────────────────────────────────────────────────────────────

function levelBadge(level: string): string {
  switch (level) {
    case "domain_concept":     return "bg-purple-500/20 text-purple-300 border-purple-500/30";
    case "feature":            return "bg-blue-500/20 text-blue-300 border-blue-500/30";
    case "functional_req":     return "bg-amber-500/20 text-amber-300 border-amber-500/30";
    case "acceptance_criterion": return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
    default:                   return "bg-buddy-border text-buddy-text-muted border-buddy-border-dark";
  }
}

function sourceTypeBadge(st: string): string {
  switch (st) {
    case "explicit":  return "bg-blue-500/10 text-blue-400 border-blue-500/20";
    case "implicit":  return "bg-gray-500/10 text-gray-400 border-gray-500/20";
    case "inferred":  return "bg-violet-500/10 text-violet-400 border-violet-500/20";
    default:          return "bg-buddy-border text-buddy-text-dim border-buddy-border-dark";
  }
}

const COLOR_ICON: Record<string, string> = {
  green:  "🟢",
  yellow: "🟡",
  orange: "🟠",
  red:    "🔴",
};

// ── RequirementCard ──────────────────────────────────────────────────────────

interface CardProps {
  req: Requirement;
  onMarkReviewed: (id: string) => void;
}

function RequirementCard({ req, onMarkReviewed }: CardProps) {
  const [expanded, setExpanded] = useState(false);
  const confidencePct = req.confidence != null
    ? Math.round(req.confidence * 100)
    : null;

  return (
    <div
      className={`rounded-lg border bg-buddy-elevated p-3 transition-all ${
        req.needs_review
          ? "border-l-4 border-amber-400 border-r border-t border-b border-buddy-border"
          : "border border-buddy-border"
      }`}
      style={req.needs_review ? { borderLeftColor: "#c8902a" } : undefined}
    >
      {/* Top row */}
      <div className="flex items-start gap-2">
        {req.external_id && (
          <span className="shrink-0 font-mono text-[10px] px-1.5 py-0.5 rounded border bg-buddy-border text-buddy-text-dim border-buddy-border-dark">
            {req.external_id}
          </span>
        )}
        <span className="flex-1 text-sm font-medium text-buddy-text leading-snug">
          {req.title}
        </span>
        {confidencePct != null && (
          <span className="shrink-0 text-[10px] font-mono text-buddy-text-muted">
            {confidencePct}%
          </span>
        )}
      </div>

      {/* Description */}
      {req.description && (
        <p
          className={`mt-1.5 text-xs text-buddy-text-muted leading-relaxed ${
            expanded ? "" : "line-clamp-2"
          }`}
        >
          {req.description}
        </p>
      )}
      {req.description && req.description.length > 120 && (
        <button
          onClick={() => setExpanded((e) => !e)}
          className="mt-0.5 text-[10px] text-buddy-gold hover:text-buddy-gold-light transition-colors"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}

      {/* Bottom row: badges + action */}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${levelBadge(req.level)}`}
        >
          {req.level.replace("_", " ")}
        </span>
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded border ${sourceTypeBadge(req.source_type)}`}
        >
          {req.source_type}
        </span>
        {req.needs_review && (
          <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-400/40 bg-amber-400/10 text-amber-400 font-medium">
            needs review
          </span>
        )}

        <div className="ml-auto">
          {req.human_reviewed ? (
            <span className="text-[10px] text-emerald-400 flex items-center gap-1">
              <span>✓</span> Reviewed
            </span>
          ) : (
            <button
              onClick={() => onMarkReviewed(req.id)}
              className="text-[10px] px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
            >
              ✓ Mark as reviewed
            </button>
          )}
        </div>
      </div>

      {/* Review reason */}
      {req.review_reason && (
        <p className="mt-1.5 text-[10px] text-amber-400/70 italic">{req.review_reason}</p>
      )}
    </div>
  );
}

// ── HeatmapSection ────────────────────────────────────────────────────────────

interface HeatmapSectionProps {
  projectId: string;
}

function HeatmapSection({ projectId }: HeatmapSectionProps) {
  const { heatmap, loading } = useHeatmap(projectId);
  const [open, setOpen] = useState(true);

  return (
    <div className="border border-buddy-border rounded-xl overflow-hidden bg-buddy-surface">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-buddy-elevated/50 transition-colors"
      >
        <span className="text-sm font-semibold text-buddy-text">
          📊 Coverage Heatmap
        </span>
        <span className="ml-auto text-xs text-buddy-text-faint">
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div className="border-t border-buddy-border">
          {loading ? (
            <div className="px-4 py-6 flex items-center gap-2 text-xs text-buddy-text-muted">
              <span className="animate-spin">⟳</span> Loading heatmap…
            </div>
          ) : heatmap.length === 0 ? (
            <div className="px-4 py-6 text-xs text-buddy-text-faint">
              Run Mapping workflow first to see coverage scores.
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-buddy-border">
                  <th className="text-left px-4 py-2 text-buddy-text-faint font-medium">Module</th>
                  <th className="text-right px-4 py-2 text-buddy-text-faint font-medium">Requirements</th>
                  <th className="text-right px-4 py-2 text-buddy-text-faint font-medium">Covered</th>
                  <th className="text-right px-4 py-2 text-buddy-text-faint font-medium">Avg Score</th>
                  <th className="text-center px-4 py-2 text-buddy-text-faint font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {heatmap.map((row) => (
                  <tr
                    key={row.module}
                    className="border-b border-buddy-border last:border-0 hover:bg-buddy-elevated/50 transition-colors"
                  >
                    <td className="px-4 py-2.5 text-buddy-text font-medium font-mono">
                      {row.module}
                    </td>
                    <td className="px-4 py-2.5 text-right text-buddy-text-muted">
                      {row.total_requirements}
                    </td>
                    <td className="px-4 py-2.5 text-right text-buddy-text-muted">
                      {row.covered}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-buddy-text-muted">
                      {row.avg_score.toFixed(1)}
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <span title={row.color}>
                        {COLOR_ICON[row.color] ?? "⬜"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

// ── RequirementsRegistry ──────────────────────────────────────────────────────

interface RegistryProps {
  requirements: Requirement[];
  stats: import("@/lib/useRequirements").RequirementsStats | null;
  loading: boolean;
  onMarkReviewed: (id: string) => void;
  projectId: string;
}

function RequirementsRegistry({ requirements, stats, loading, onMarkReviewed, projectId }: RegistryProps) {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  const filtered = useMemo(() => {
    if (!search.trim()) return requirements;
    const q = search.toLowerCase();
    return requirements.filter(
      (r) =>
        r.title.toLowerCase().includes(q) ||
        (r.description ?? "").toLowerCase().includes(q) ||
        (r.external_id ?? "").toLowerCase().includes(q)
    );
  }, [requirements, search]);

  const groups = useMemo(() => {
    const map = new Map<string, Requirement[]>();
    for (const r of filtered) {
      const key = r.taxonomy?.module ?? "Other";
      const arr = map.get(key) ?? [];
      arr.push(r);
      map.set(key, arr);
    }
    // Sort: "Other" last
    const sorted = [...map.entries()].sort(([a], [b]) => {
      if (a === "Other") return 1;
      if (b === "Other") return -1;
      return a.localeCompare(b);
    });
    return sorted;
  }, [filtered]);

  const toggleGroup = (key: string) =>
    setOpenGroups((prev) => ({ ...prev, [key]: !(prev[key] ?? true) }));

  const isOpen = (key: string) => openGroups[key] ?? true;

  return (
    <div className="flex flex-col gap-3 flex-1 min-h-0">
      {/* Header + stats */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-semibold text-buddy-text">
          📋 Requirements Registry
        </span>
        {stats && (
          <>
            <span className="text-[10px] px-2 py-0.5 rounded border border-buddy-border bg-buddy-elevated text-buddy-text-muted font-mono">
              {stats.total} total
            </span>
            {stats.needs_review_count > 0 && (
              <span className="text-[10px] px-2 py-0.5 rounded border border-amber-400/30 bg-amber-400/10 text-amber-400 font-mono">
                {stats.needs_review_count} needs review
              </span>
            )}
            {stats.human_reviewed_count > 0 && (
              <span className="text-[10px] px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 font-mono">
                {stats.human_reviewed_count} reviewed
              </span>
            )}
          </>
        )}
      </div>

      {/* Search */}
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Filter by title, description or ID…"
        className="w-full bg-buddy-elevated border border-buddy-border-dark rounded-lg text-xs text-buddy-text placeholder:text-buddy-text-faint px-3 py-2 focus:outline-none focus:border-buddy-gold"
      />

      {/* Body */}
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-buddy-text-muted py-6 justify-center">
          <span className="animate-spin">⟳</span> Loading requirements…
        </div>
      ) : requirements.length === 0 ? (
        <div className="flex flex-col items-center gap-4 py-12 px-6 text-center">
          <span className="text-4xl leading-none">📋</span>
          <div>
            <p className="text-sm font-medium text-buddy-text mb-1">
              Nie wyodrębniono jeszcze wymagań
            </p>
            <p className="text-xs text-buddy-text-muted leading-relaxed max-w-sm">
              Najpierw zbuduj kontekst w{" "}
              <span className="text-buddy-text font-medium">🧠 Context Builder</span>, wgrywając
              dokumentację projektu. Potem wróć tutaj i kliknij{" "}
              <span className="text-buddy-text font-medium">„Wyodrębnij wymagania"</span>.
            </p>
          </div>
          <button
            onClick={() => router.push(`/context/${encodeURIComponent(projectId)}`)}
            className="px-4 py-2 bg-gradient-to-r from-buddy-gold to-buddy-gold-light text-buddy-surface text-xs font-semibold rounded-lg hover:opacity-90 transition-opacity"
          >
            Przejdź do Context Builder →
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-xs text-buddy-text-faint text-center py-10">
          No requirements match your search.
        </div>
      ) : (
        <div className="flex flex-col gap-3 overflow-y-auto flex-1 pr-1">
          {groups.map(([groupKey, items]) => {
            const open = isOpen(groupKey);
            return (
              <div
                key={groupKey}
                className="border border-buddy-border rounded-xl overflow-hidden bg-buddy-surface"
              >
                <button
                  onClick={() => toggleGroup(groupKey)}
                  className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-buddy-elevated/50 transition-colors"
                >
                  <span className="text-xs font-semibold text-buddy-text-muted font-mono">
                    {groupKey}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-buddy-border text-buddy-text-dim font-mono">
                    {items.length}
                  </span>
                  <span className="ml-auto text-[10px] text-buddy-text-faint">
                    {open ? "▲" : "▼"}
                  </span>
                </button>

                {open && (
                  <div className="border-t border-buddy-border p-3 flex flex-col gap-2">
                    {items.map((req) => (
                      <RequirementCard
                        key={req.id}
                        req={req}
                        onMarkReviewed={onMarkReviewed}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RequirementsPage({
  params,
}: {
  params: { projectId: string };
}) {
  const projectId = decodeURIComponent(params.projectId);

  const { files: projectFiles, uploading, uploadFiles } = useProjectFiles(projectId);
  const { status: contextStatus } = useContextBuilder(projectId);
  const { requirements, stats, loading, patchRequirement } = useRequirements(projectId);

  const handleMarkReviewed = (id: string) => {
    patchRequirement(id, { human_reviewed: true, needs_review: false });
  };

  return (
    <div className="flex h-screen overflow-hidden bg-buddy-base text-buddy-text font-sans">
      <Sidebar
        activeProjectId={projectId}
        projectFiles={projectFiles}
        onUploadFiles={uploadFiles}
        isUploading={uploading}
        contextReady={contextStatus?.rag_ready}
        activeModule="requirements"
      />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <div className="px-6 py-3.5 border-b border-buddy-border bg-buddy-surface flex items-center gap-3 shrink-0">
          <div className="flex-1 min-w-0">
            <div className="text-[15px] font-semibold text-buddy-text">
              📋 Requirements Registry
            </div>
            <div className="text-xs text-buddy-text-dim">
              Faza 2 — Requirements Extraction &amp; Review
            </div>
          </div>
          {stats && (
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-buddy-border text-buddy-text-muted border border-buddy-border-dark">
                {stats.total} reqs
              </span>
              {stats.needs_review_count > 0 && (
                <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-amber-400/10 text-amber-400 border border-amber-400/20">
                  {stats.needs_review_count} to review
                </span>
              )}
            </div>
          )}
        </div>

        {/* Main content */}
        <div className="flex-1 flex flex-col gap-4 overflow-hidden p-5">
          {/* Section A: Heatmap */}
          <div className="shrink-0">
            <HeatmapSection projectId={projectId} />
          </div>

          {/* Section B: Registry */}
          <RequirementsRegistry
            requirements={requirements}
            stats={stats}
            loading={loading}
            onMarkReviewed={handleMarkReviewed}
            projectId={projectId}
          />
        </div>
      </div>
    </div>
  );
}
