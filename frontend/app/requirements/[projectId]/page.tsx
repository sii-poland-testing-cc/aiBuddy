"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useProjectFiles } from "@/lib/useProjectFiles";
import { useContextBuilder } from "@/lib/useContextBuilder";
import { useRequirements, type Requirement } from "@/lib/useRequirements";
import { useHeatmap } from "@/lib/useHeatmap";
import Sidebar from "@/components/Sidebar";
import ErrorBanner from "@/components/ErrorBanner";

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
      className={`rounded-lg bg-buddy-elevated p-3 transition-all ${
        req.needs_review
          ? "border border-buddy-border border-l-4 border-l-amber-500"
          : "border border-buddy-border"
      }`}
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
          aria-expanded={expanded}
          className="mt-0.5 text-[10px] text-buddy-gold hover:text-buddy-gold-light transition-colors"
        >
          {expanded ? "Zwiń" : "Rozwiń"}
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
            do przeglądu
          </span>
        )}

        <div className="ml-auto">
          {req.human_reviewed ? (
            <span className="text-[10px] text-emerald-400 flex items-center gap-1">
              <span>✓</span> Zweryfikowane
            </span>
          ) : (
            <button
              onClick={() => onMarkReviewed(req.id)}
              className="text-[10px] px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
            >
              ✓ Oznacz jako zweryfikowane
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
  const { heatmap, loading, error, retry } = useHeatmap(projectId);
  const [open, setOpen] = useState(true);

  return (
    <div className="border border-buddy-border rounded-xl overflow-hidden bg-buddy-surface">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-buddy-elevated/50 transition-colors"
      >
        <span className="text-sm font-semibold text-buddy-text">
          📊 Heatmapa pokrycia
        </span>
        <span className="ml-auto text-xs text-buddy-text-faint">
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div className="border-t border-buddy-border">
          {error ? (
            <div className="p-3">
              <ErrorBanner message={error} onRetry={retry} />
            </div>
          ) : loading ? (
            <div className="p-3 animate-pulse">
              <div className="border border-buddy-border rounded-lg overflow-hidden">
                <div className="flex border-b border-buddy-border px-4 py-2 gap-4">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <div key={i} className="h-3 flex-1 bg-buddy-border rounded" />
                  ))}
                </div>
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex border-b border-buddy-border last:border-0 px-4 py-2.5 gap-4">
                    {[1, 2, 3, 4, 5].map((j) => (
                      <div key={j} className="h-3 flex-1 bg-buddy-elevated rounded" />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          ) : heatmap.length === 0 ? (
            <div className="px-4 py-6 text-xs text-buddy-text-faint">
              Uruchom Mapping, by zobaczyć wyniki pokrycia.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-buddy-border">
                    <th className="text-left px-4 py-2 text-buddy-text-faint font-medium">Moduł</th>
                    <th className="text-right px-4 py-2 text-buddy-text-faint font-medium">Wymagania</th>
                    <th className="text-right px-4 py-2 text-buddy-text-faint font-medium">Pokryte</th>
                    <th className="text-right px-4 py-2 text-buddy-text-faint font-medium">Śr. wynik</th>
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
            </div>
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
  onExtract: () => void;
  isExtracting: boolean;
  contextReady: boolean;
}

function RequirementsRegistry({ requirements, stats, loading, onMarkReviewed, projectId, onExtract, isExtracting, contextReady }: RegistryProps) {
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
    <div className="flex flex-col gap-3">
      {/* Header + stats */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-semibold text-buddy-text">
          📋 Rejestr wymagań
        </span>
        {stats && (
          <>
            <span className="text-[10px] px-2 py-0.5 rounded border border-buddy-border bg-buddy-elevated text-buddy-text-muted font-mono">
              {stats.total} łącznie
            </span>
            {stats.needs_review_count > 0 && (
              <span className="text-[10px] px-2 py-0.5 rounded border border-amber-400/30 bg-amber-400/10 text-amber-400 font-mono">
                {stats.needs_review_count} do przeglądu
              </span>
            )}
            {stats.human_reviewed_count > 0 && (
              <span className="text-[10px] px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 font-mono">
                {stats.human_reviewed_count} zweryfikowanych
              </span>
            )}
          </>
        )}
      </div>

      {/* Search */}
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Filtruj po tytule, opisie lub ID..."
        className="w-full bg-buddy-elevated border border-buddy-border-dark rounded-lg text-xs text-buddy-text placeholder:text-buddy-text-faint px-3 py-2 focus:outline-none focus:border-buddy-gold"
      />

      {/* Body */}
      {loading ? (
        <div className="flex flex-col gap-3 py-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="rounded-lg bg-buddy-elevated border border-buddy-border p-3 animate-pulse">
              <div className="flex items-center gap-2 mb-2">
                <div className="h-3 w-14 bg-buddy-border rounded" />
                <div className="h-3 flex-1 bg-buddy-border rounded" />
                <div className="h-3 w-8 bg-buddy-border rounded" />
              </div>
              <div className="h-2.5 w-3/4 bg-buddy-border rounded mb-1.5" />
              <div className="h-2.5 w-1/2 bg-buddy-border rounded" />
              <div className="flex gap-1.5 mt-2">
                <div className="h-4 w-16 bg-buddy-border rounded" />
                <div className="h-4 w-12 bg-buddy-border rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : requirements.length === 0 ? (
        <div className="flex flex-col items-center gap-4 py-12 px-6 text-center">
          <span className="text-4xl leading-none">📋</span>
          <div>
            <p className="text-sm font-medium text-buddy-text mb-1">
              Nie wyodrębniono jeszcze wymagań
            </p>
            {contextReady ? (
              <p className="text-xs text-buddy-text-muted leading-relaxed max-w-sm">
                Kontekst projektu jest gotowy. Kliknij przycisk poniżej, aby wyodrębnić wymagania z dokumentacji.
              </p>
            ) : (
              <p className="text-xs text-buddy-text-muted leading-relaxed max-w-sm">
                Najpierw zbuduj kontekst w{" "}
                <span className="text-buddy-text font-medium">🧠 Context Builder</span>, wgrywając
                dokumentację projektu.
              </p>
            )}
          </div>
          {contextReady ? (
            <button
              onClick={onExtract}
              disabled={isExtracting}
              className="px-4 py-2 bg-gradient-to-r from-buddy-gold to-buddy-gold-light text-buddy-surface text-xs font-semibold rounded-lg hover:opacity-90 disabled:opacity-40 transition-opacity"
            >
              {isExtracting ? "Wyodrębnianie…" : "Wyodrębnij wymagania"}
            </button>
          ) : (
            <button
              onClick={() => router.push(`/context/${encodeURIComponent(projectId)}`)}
              className="px-4 py-2 bg-gradient-to-r from-buddy-gold to-buddy-gold-light text-buddy-surface text-xs font-semibold rounded-lg hover:opacity-90 transition-opacity"
            >
              Przejdź do Context Builder →
            </button>
          )}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-xs text-buddy-text-faint text-center py-10">
          Brak wymagań pasujących do wyszukiwania.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
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

// ── Re-extract confirmation modal ────────────────────────────────────────────

function ReExtractModal({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  return (
    <div
      className="fixed inset-0 bg-black/65 flex items-center justify-center z-50"
      onClick={onCancel}
      role="dialog"
      aria-labelledby="re-extract-modal-title"
    >
      <div
        className="bg-buddy-elevated border border-buddy-border-dark rounded-xl p-6 max-w-[360px] w-[90%] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div id="re-extract-modal-title" className="text-[15px] font-semibold text-buddy-gold-light mb-2.5">
          Wyodrębnić ponownie?
        </div>
        <div className="text-[13px] text-[#c8b89a] leading-relaxed mb-5">
          Ponowne wyodrębnienie zastąpi istniejące wymagania. Kontynuować?
        </div>
        <div className="flex gap-2.5 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-[7px] rounded-lg border border-buddy-border-dark bg-transparent text-[#c8b89a] text-[13px] cursor-pointer hover:bg-buddy-border transition-colors"
          >
            Anuluj
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-[7px] rounded-lg border-none bg-buddy-gold text-buddy-surface text-[13px] font-semibold cursor-pointer hover:opacity-90 transition-opacity"
          >
            Wyodrębnij ponownie
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Mapping SSE hook ─────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface MappingProgress {
  message: string;
  progress: number;
  stage: string;
}

function useMappingRunner(projectId: string) {
  const [isMapping, setIsMapping] = useState(false);
  const [mappingProgress, setMappingProgress] = useState<MappingProgress | null>(null);
  const [mappingError, setMappingError] = useState<string | null>(null);

  const runMapping = async (onComplete?: () => void) => {
    if (!projectId || isMapping) return;
    setIsMapping(true);
    setMappingError(null);
    setMappingProgress({ message: "Łączenie z serwerem…", progress: 0, stage: "load" });

    try {
      const res = await fetch(`${API_BASE}/api/mapping/${projectId}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });

      if (!res.ok) throw new Error(`Server error ${res.status}`);
      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") break;
          try {
            const ev = JSON.parse(payload);
            if (ev.type === "progress") {
              setMappingProgress(ev.data as MappingProgress);
            } else if (ev.type === "result") {
              onComplete?.();
            } else if (ev.type === "error") {
              setMappingError(ev.data?.message ?? "Mapowanie nie powiodło się.");
            }
          } catch {
            // malformed line — skip
          }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setMappingError(
        msg.includes("Server error") || msg.includes("No response")
          ? msg
          : "Nie udało się uruchomić mapowania. Sprawdź połączenie z serwerem."
      );
    } finally {
      setIsMapping(false);
      setMappingProgress(null);
    }
  };

  return { isMapping, mappingProgress, mappingError, runMapping };
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
  const {
    requirements, stats, loading,
    error: reqError, isExtracting, extractionProgress,
    patchRequirement, extractRequirements, retry: retryRequirements,
  } = useRequirements(projectId);
  const { heatmap, retry: retryHeatmap } = useHeatmap(projectId);
  const { isMapping, mappingProgress, mappingError, runMapping } = useMappingRunner(projectId);

  const contextReady = contextStatus?.rag_ready ?? false;
  const [showReExtractModal, setShowReExtractModal] = useState(false);

  const handleMarkReviewed = (id: string) => {
    patchRequirement(id, { human_reviewed: true, needs_review: false });
  };

  const handleExtractClick = () => {
    if (requirements.length > 0) {
      setShowReExtractModal(true);
    } else {
      extractRequirements();
    }
  };

  const confirmReExtract = () => {
    setShowReExtractModal(false);
    extractRequirements();
  };

  const handleRunMapping = () => {
    runMapping(() => {
      retryHeatmap();
    });
  };

  // Determine progress to show (extraction or mapping)
  const activeProgress = isExtracting && extractionProgress
    ? extractionProgress
    : isMapping && mappingProgress
      ? mappingProgress
      : null;

  return (
    <div className="flex h-screen overflow-hidden bg-buddy-base text-buddy-text font-sans">
      {showReExtractModal && (
        <ReExtractModal
          onConfirm={confirmReExtract}
          onCancel={() => setShowReExtractModal(false)}
        />
      )}

      <Sidebar
        activeProjectId={projectId}
        projectFiles={projectFiles}
        onUploadFiles={uploadFiles}
        isUploading={uploading}
        contextReady={contextReady}
        activeModule="requirements"
      />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <div className="pl-14 md:pl-6 pr-6 py-3.5 border-b border-buddy-border bg-buddy-surface flex items-center gap-3 shrink-0">
          <div className="flex-1 min-w-0">
            <div className="text-[15px] font-semibold text-buddy-text">
              📋 Rejestr wymagań
            </div>
            <div className="text-xs text-buddy-text-dim">
              Faza 2 — Ekstrakcja i przegląd wymagań
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {stats && (
              <>
                <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-buddy-border text-buddy-text-muted border border-buddy-border-dark">
                  {stats.total} wymagań
                </span>
                {stats.needs_review_count > 0 && (
                  <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-amber-400/10 text-amber-400 border border-amber-400/20">
                    {stats.needs_review_count} do przeglądu
                  </span>
                )}
              </>
            )}
            {/* Run Mapping button — visible when requirements exist */}
            {requirements.length > 0 && (
              <button
                onClick={handleRunMapping}
                disabled={isMapping || isExtracting}
                title={isMapping ? "Mapowanie w toku…" : undefined}
                className="px-3 py-1.5 bg-buddy-elevated border border-buddy-border-dark text-buddy-text-muted text-xs font-semibold rounded-lg hover:border-buddy-gold hover:text-buddy-gold-light disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                {isMapping
                  ? "Mapowanie…"
                  : heatmap.length > 0
                    ? "↺ Uruchom ponownie mapowanie"
                    : "Uruchom mapowanie"}
              </button>
            )}
            <button
              onClick={handleExtractClick}
              disabled={isExtracting || !contextReady}
              title={!contextReady ? "Najpierw zbuduj kontekst w Context Builder" : undefined}
              className="px-3 py-1.5 bg-gradient-to-r from-buddy-gold to-buddy-gold-light text-buddy-surface text-xs font-semibold rounded-lg hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
            >
              {isExtracting ? "Wyodrębnianie…" : requirements.length > 0 ? "↺ Wyodrębnij ponownie" : "Wyodrębnij wymagania"}
            </button>
          </div>
        </div>

        {/* Progress bar (extraction or mapping) */}
        {activeProgress && (
          <div className="px-6 py-2 bg-buddy-gold/10 border-b border-buddy-border shrink-0">
            <div className="flex justify-between text-xs text-buddy-gold mb-1">
              <span>{activeProgress.message}</span>
              <span>{Math.round(activeProgress.progress * 100)}%</span>
            </div>
            <div className="w-full h-0.5 bg-buddy-border rounded-full overflow-hidden">
              <div
                className="h-full bg-buddy-gold rounded-full transition-all duration-300"
                style={{ width: `${activeProgress.progress * 100}%` }}
              />
            </div>
          </div>
        )}

        {/* Main content */}
        <div className="flex-1 flex flex-col gap-4 overflow-y-auto p-5">
          {reqError && (
            <div className="shrink-0">
              <ErrorBanner message={reqError} onRetry={retryRequirements} onDismiss={retryRequirements} />
            </div>
          )}
          {mappingError && (
            <div className="shrink-0">
              <ErrorBanner message={mappingError} />
            </div>
          )}

          {/* Section A: Heatmap */}
          <div className="shrink-0 max-h-[40vh] overflow-y-auto">
            <HeatmapSection projectId={projectId} />
          </div>

          {/* Section B: Registry */}
          <RequirementsRegistry
            requirements={requirements}
            stats={stats}
            loading={loading}
            onMarkReviewed={handleMarkReviewed}
            projectId={projectId}
            onExtract={handleExtractClick}
            isExtracting={isExtracting}
            contextReady={contextReady}
          />
        </div>
      </div>
    </div>
  );
}
