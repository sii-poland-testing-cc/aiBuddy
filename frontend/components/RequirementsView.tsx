"use client";

import { useState, useMemo } from "react";
import type { Requirement, RequirementsStats } from "@/lib/useRequirements";

// ── Helpers ────────────────────────────────────────────────────────────────────

function levelColor(level: string): { bg: string; text: string; border: string } {
  switch (level) {
    case "domain_concept":
      return { bg: "rgba(155,107,191,0.15)", text: "#b07fe0", border: "rgba(155,107,191,0.3)" };
    case "feature":
      return { bg: "rgba(91,127,186,0.15)", text: "#7aa0d4", border: "rgba(91,127,186,0.3)" };
    case "functional_req":
      return { bg: "rgba(200,144,42,0.15)", text: "#c8902a", border: "rgba(200,144,42,0.3)" };
    case "acceptance_criterion":
      return { bg: "rgba(74,158,107,0.15)", text: "#4a9e6b", border: "rgba(74,158,107,0.3)" };
    default:
      return { bg: "rgba(42,37,32,0.5)", text: "#7a6e64", border: "#3a342c" };
  }
}

function sourceColor(st: string): { bg: string; text: string; border: string } {
  switch (st) {
    case "formal":
      return { bg: "rgba(91,127,186,0.1)", text: "#7aa0d4", border: "rgba(91,127,186,0.2)" };
    case "implicit":
      return { bg: "rgba(106,106,106,0.12)", text: "#8a8a8a", border: "rgba(106,106,106,0.2)" };
    case "reconstructed":
      return { bg: "rgba(155,107,191,0.1)", text: "#b07fe0", border: "rgba(155,107,191,0.2)" };
    default:
      return { bg: "rgba(42,37,32,0.5)", text: "#7a6e64", border: "#3a342c" };
  }
}

function lifecycleColor(status: string | null | undefined): { bg: string; text: string; border: string } {
  switch (status) {
    case "draft":     return { bg: "rgba(100,100,100,0.12)", text: "#9a9a9a", border: "rgba(100,100,100,0.25)" };
    case "active":    return { bg: "rgba(96,165,250,0.12)", text: "#60a5fa", border: "rgba(96,165,250,0.25)" };
    case "ready":     return { bg: "rgba(200,144,42,0.12)", text: "#c8902a", border: "rgba(200,144,42,0.25)" };
    case "promoted":  return { bg: "rgba(74,158,107,0.12)", text: "#4a9e6b", border: "rgba(74,158,107,0.25)" };
    case "conflict_pending": return { bg: "rgba(200,90,58,0.12)", text: "#c85a3a", border: "rgba(200,90,58,0.25)" };
    default:          return { bg: "rgba(42,37,32,0.5)", text: "#7a6e64", border: "#3a342c" };
  }
}

// ── RequirementCard ────────────────────────────────────────────────────────────

interface CardProps {
  req: Requirement;
  onMarkReviewed: (id: string) => void;
  currentContextId?: string | null;
  contexts?: import("../lib/useWorkContext").WorkContext[];
}

function RequirementCard({ req, onMarkReviewed, currentContextId, contexts }: CardProps) {
  const [expanded, setExpanded] = useState(false);
  const pct = req.confidence != null ? Math.round(req.confidence * 100) : null;
  const lc = levelColor(req.level);
  const sc = sourceColor(req.source_type);
  const longDesc = req.description && req.description.length > 120;
  const isContextItem = !!(req.lifecycle_status && req.lifecycle_status !== "promoted");

  return (
    <div
      data-testid="req-card"
      className="bg-buddy-elevated rounded-lg"
      style={{
        border: isContextItem && currentContextId
          ? `1px solid ${lifecycleColor(req.lifecycle_status).border}`
          : req.needs_review
          ? "1px solid rgba(245,158,11,0.5)"
          : "1px solid var(--buddy-border, #2a2520)",
        borderLeft: isContextItem && currentContextId
          ? `3px solid ${lifecycleColor(req.lifecycle_status).text}`
          : req.needs_review
          ? "3px solid #f59e0b"
          : undefined,
        padding: "10px 12px",
      }}
    >
      {/* Top row */}
      <div className="flex items-start gap-2">
        {req.external_id && (
          <span
            className="shrink-0 font-mono"
            style={{
              fontSize: 10, padding: "1px 6px", borderRadius: 3,
              background: "rgba(42,37,32,0.6)", color: "#a09078",
              border: "1px solid #3a342c",
            }}
          >
            {req.external_id}
          </span>
        )}
        <span className="flex-1 font-medium text-buddy-text" style={{ fontSize: 13, lineHeight: 1.4 }}>
          {req.title}
        </span>
        {pct != null && (
          <span
            className="shrink-0 font-mono text-buddy-text-muted"
            style={{ fontSize: 10 }}
            title="Confidence"
          >
            {pct}%
          </span>
        )}
      </div>

      {/* Description */}
      {req.description && (
        <>
          <p
            className="text-buddy-text-muted"
            style={{
              fontSize: 11,
              lineHeight: 1.5,
              marginTop: 6,
              overflow: "hidden",
              display: "-webkit-box",
              WebkitLineClamp: expanded ? "unset" : 2,
              WebkitBoxOrient: "vertical",
            }}
          >
            {req.description}
          </p>
          {longDesc && (
            <button
              onClick={() => setExpanded((e) => !e)}
              className="text-buddy-gold hover:text-buddy-gold-light transition-colors"
              style={{ fontSize: 10, marginTop: 2 }}
            >
              {expanded ? "Zwiń" : "Rozwiń"}
            </button>
          )}
        </>
      )}

      {/* Badges + action */}
      <div className="flex flex-wrap items-center gap-1.5" style={{ marginTop: 8 }}>
        <span
          className="font-medium"
          style={{
            fontSize: 10, padding: "1px 6px", borderRadius: 3,
            background: lc.bg, color: lc.text, border: `1px solid ${lc.border}`,
          }}
        >
          {req.level.replace(/_/g, " ")}
        </span>
        <span
          style={{
            fontSize: 10, padding: "1px 6px", borderRadius: 3,
            background: sc.bg, color: sc.text, border: `1px solid ${sc.border}`,
          }}
        >
          {req.source_type}
        </span>
        {req.lifecycle_status && req.lifecycle_status !== "promoted" && (
          <span
            style={{
              fontSize: 10, padding: "1px 6px", borderRadius: 3,
              background: lifecycleColor(req.lifecycle_status).bg,
              color: lifecycleColor(req.lifecycle_status).text,
              border: `1px solid ${lifecycleColor(req.lifecycle_status).border}`,
            }}
          >
            {req.lifecycle_status}
          </span>
        )}
        {req.work_context_id && contexts && (() => {
          const ctxName = contexts.find((c) => c.id === req.work_context_id)?.name;
          if (!ctxName) return null;
          return (
            <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3, background: "rgba(42,37,32,0.4)", color: "#7a6e64", border: "1px solid #3a342c" }}>
              📍 {ctxName}
            </span>
          );
        })()}
        {req.needs_review && (
          <span
            style={{
              fontSize: 10, padding: "1px 6px", borderRadius: 3,
              background: "rgba(245,158,11,0.1)", color: "#f59e0b",
              border: "1px solid rgba(245,158,11,0.3)", fontWeight: 600,
            }}
          >
            do przeglądu
          </span>
        )}
        {req.review_reason && (
          <span className="text-amber-400/70 italic" style={{ fontSize: 10 }}>
            {req.review_reason}
          </span>
        )}

        <div className="ml-auto">
          {req.human_reviewed ? (
            <span className="flex items-center gap-1" style={{ fontSize: 10, color: "#4a9e6b" }}>
              ✓ Zweryfikowane
            </span>
          ) : (
            <button
              onClick={() => onMarkReviewed(req.id)}
              className="transition-colors"
              style={{
                fontSize: 10, padding: "1px 8px", borderRadius: 3,
                background: "rgba(74,158,107,0.1)", color: "#4a9e6b",
                border: "1px solid rgba(74,158,107,0.3)",
                cursor: "pointer",
              }}
            >
              ✓ Oznacz jako zweryfikowane
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Module group ───────────────────────────────────────────────────────────────

function ModuleGroup({
  label,
  items,
  onMarkReviewed,
  currentContextId,
  contexts,
}: {
  label: string;
  items: Requirement[];
  onMarkReviewed: (id: string) => void;
  currentContextId?: string | null;
  contexts?: import("../lib/useWorkContext").WorkContext[];
}) {
  const [open, setOpen] = useState(true);
  return (
    <div
      data-testid="req-module-group"
      className="bg-buddy-surface border border-buddy-border-light overflow-hidden"
      style={{ borderRadius: 6 }}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 text-left hover:bg-buddy-elevated/50 transition-colors"
        style={{ padding: "8px 14px" }}
        aria-expanded={open}
      >
        <span className="font-mono font-semibold text-buddy-text-muted" style={{ fontSize: 11 }}>
          {label}
        </span>
        <span
          className="font-mono text-buddy-text-dim"
          style={{
            fontSize: 10, padding: "0 5px", borderRadius: 3,
            background: "rgba(42,37,32,0.6)", border: "1px solid #3a342c",
          }}
        >
          {items.length}
        </span>
        <span className="ml-auto text-buddy-text-faint" style={{ fontSize: 10 }}>
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div
          className="flex flex-col gap-2 border-t border-buddy-border"
          style={{ padding: "10px 12px" }}
        >
          {items.map((req) => (
            <RequirementCard key={req.id} req={req} onMarkReviewed={onMarkReviewed} currentContextId={currentContextId} contexts={contexts} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── RequirementsView ───────────────────────────────────────────────────────────

interface RequirementsViewProps {
  requirements: Requirement[];
  stats: RequirementsStats | null;
  loading: boolean;
  error: string | null;
  contextReady: boolean;
  onExtract: () => void;
  onMarkReviewed: (id: string) => void;
  currentContextId?: string | null;
  contexts?: import("../lib/useWorkContext").WorkContext[];
}

export default function RequirementsView({
  requirements,
  stats,
  loading,
  error,
  contextReady,
  onExtract,
  onMarkReviewed,
  currentContextId,
  contexts,
}: RequirementsViewProps) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);

  const filtered = useMemo(() => {
    let result = requirements;
    if (statusFilter) {
      result = result.filter((r) => (r.lifecycle_status ?? "promoted") === statusFilter);
    }
    if (!search.trim()) return result;
    const q = search.toLowerCase();
    return result.filter(
      (r) =>
        r.title.toLowerCase().includes(q) ||
        (r.description ?? "").toLowerCase().includes(q) ||
        (r.external_id ?? "").toLowerCase().includes(q)
    );
  }, [requirements, search, statusFilter]);

  const groups = useMemo(() => {
    const map = new Map<string, Requirement[]>();
    for (const r of filtered) {
      const key = r.taxonomy?.module ?? "Inne";
      const arr = map.get(key) ?? [];
      arr.push(r);
      map.set(key, arr);
    }
    // Sort within each group: context items (non-promoted) first
    for (const [, items] of map) {
      if (currentContextId) {
        items.sort((a, b) => {
          const aIsContext = a.lifecycle_status && a.lifecycle_status !== "promoted" ? 0 : 1;
          const bIsContext = b.lifecycle_status && b.lifecycle_status !== "promoted" ? 0 : 1;
          return aIsContext - bIsContext;
        });
      }
    }
    return [...map.entries()].sort(([a], [b]) => {
      if (a === "Inne") return 1;
      if (b === "Inne") return -1;
      return a.localeCompare(b);
    });
  }, [filtered, currentContextId]);

  return (
    <div className="flex flex-col h-full" style={{ padding: "0 48px" }}>

      {/* ── Sticky header ──────────────────────────────────────────────────── */}
      <div
        className="flex-shrink-0 bg-buddy-base border-b border-buddy-border"
        style={{ padding: "12px 0 10px" }}
      >
        {/* Title + stats */}
        <div className="flex items-center flex-wrap gap-2" style={{ marginBottom: 10 }}>
          <span className="font-semibold text-buddy-text" style={{ fontSize: 13 }}>
            📋 Rejestr wymagań
          </span>
          {stats && (
            <>
              <span
                className="font-mono text-buddy-text-muted"
                style={{
                  fontSize: 10, padding: "1px 7px", borderRadius: 3,
                  background: "rgba(42,37,32,0.6)", border: "1px solid #3a342c",
                }}
              >
                {stats.total} łącznie
              </span>
              {stats.needs_review_count > 0 && (
                <span
                  className="font-mono"
                  style={{
                    fontSize: 10, padding: "1px 7px", borderRadius: 3,
                    background: "rgba(245,158,11,0.1)", color: "#f59e0b",
                    border: "1px solid rgba(245,158,11,0.3)",
                  }}
                >
                  {stats.needs_review_count} do przeglądu
                </span>
              )}
              {stats.human_reviewed_count > 0 && (
                <span
                  className="font-mono"
                  style={{
                    fontSize: 10, padding: "1px 7px", borderRadius: 3,
                    background: "rgba(74,158,107,0.1)", color: "#4a9e6b",
                    border: "1px solid rgba(74,158,107,0.3)",
                  }}
                >
                  {stats.human_reviewed_count} zweryfikowanych
                </span>
              )}
            </>
          )}
          {requirements.length > 0 && (
            <button
              onClick={onExtract}
              className="ml-auto text-buddy-text-dim hover:text-buddy-gold-light hover:border-buddy-gold/40 border border-buddy-border transition-all"
              style={{ fontSize: 10, padding: "2px 8px", borderRadius: 3, background: "transparent", cursor: "pointer" }}
            >
              ↺ Wyodrębnij ponownie
            </button>
          )}
        </div>

        {/* Status filter chips (context mode) */}
        {currentContextId && requirements.length > 0 && (
          <div className="flex gap-1.5 flex-wrap" style={{ marginBottom: 8 }}>
            {["promoted", "active", "ready", "draft"].map((status) => {
              const count = requirements.filter((r) => (r.lifecycle_status ?? "promoted") === status).length;
              if (count === 0) return null;
              const lc = lifecycleColor(status);
              return (
                <button
                  key={status}
                  onClick={() => setStatusFilter((f) => f === status ? null : status)}
                  style={{
                    fontSize: 10, padding: "2px 8px", borderRadius: 12, cursor: "pointer",
                    background: statusFilter === status ? lc.bg : "rgba(42,37,32,0.3)",
                    color: statusFilter === status ? lc.text : "#7a6e64",
                    border: `1px solid ${statusFilter === status ? lc.border : "#3a342c"}`,
                  }}
                >
                  {status} ({count})
                </button>
              );
            })}
            {statusFilter && (
              <button onClick={() => setStatusFilter(null)} style={{ fontSize: 10, color: "#7a6e64", background: "none", border: "none", cursor: "pointer" }}>
                ✕ clear
              </button>
            )}
          </div>
        )}

        {/* Search */}
        <input
          data-testid="req-search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filtruj po tytule, opisie lub ID…"
          className="w-full bg-buddy-elevated border border-buddy-border text-buddy-text placeholder:text-buddy-text-faint focus:outline-none focus:border-buddy-gold/50 transition-colors"
          style={{ padding: "6px 10px", borderRadius: 5, fontSize: 12 }}
        />
      </div>

      {/* ── Scrollable body ────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto" style={{ padding: "12px 0 24px" }}>

        {/* Error */}
        {error && (
          <div
            className="border border-red-800/40 bg-red-900/10 text-red-400 rounded-lg"
            style={{ padding: "10px 14px", fontSize: 12, marginBottom: 12 }}
          >
            ⚠ {error}
          </div>
        )}

        {/* Loading skeletons */}
        {loading && !requirements.length && (
          <div className="flex flex-col gap-3">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="bg-buddy-elevated border border-buddy-border rounded-lg animate-pulse"
                style={{ padding: "12px 14px" }}
              >
                <div className="flex gap-2 mb-2">
                  <div className="h-3 w-14 bg-buddy-border rounded" />
                  <div className="h-3 flex-1 bg-buddy-border rounded" />
                  <div className="h-3 w-8 bg-buddy-border rounded" />
                </div>
                <div className="h-2.5 w-3/4 bg-buddy-border rounded mb-1.5" />
                <div className="h-2.5 w-1/2 bg-buddy-border rounded" />
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && requirements.length === 0 && (
          <div
            data-testid="req-empty-state"
            className="flex flex-col items-center gap-4 text-center"
            style={{ paddingTop: 64, paddingBottom: 48 }}
          >
            <span style={{ fontSize: 40, lineHeight: 1 }}>📋</span>
            <div>
              <p className="font-medium text-buddy-text" style={{ fontSize: 14, marginBottom: 6 }}>
                Nie wyodrębniono jeszcze wymagań
              </p>
              {currentContextId ? (
                <p className="text-buddy-text-muted" style={{ fontSize: 12, lineHeight: 1.5, maxWidth: 340 }}>
                  No artifacts in this context yet. Run context builder or extract requirements to populate.
                </p>
              ) : contextReady ? (
                <p className="text-buddy-text-muted" style={{ fontSize: 12, lineHeight: 1.5, maxWidth: 340 }}>
                  Kontekst projektu jest gotowy. Kliknij przycisk poniżej, aby wyodrębnić wymagania z dokumentacji.
                </p>
              ) : (
                <p className="text-buddy-text-muted" style={{ fontSize: 12, lineHeight: 1.5, maxWidth: 340 }}>
                  Najpierw zbuduj kontekst w <strong className="text-buddy-text">🧠 Context Builder</strong>, wgrywając dokumentację projektu.
                </p>
              )}
            </div>
            <button
              data-testid="extract-btn"
              onClick={onExtract}
              disabled={!contextReady}
              className="font-semibold text-buddy-surface hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
              style={{
                padding: "8px 20px",
                borderRadius: 6,
                fontSize: 13,
                background: "linear-gradient(135deg, #c8902a, #e0aa42)",
                border: "none",
                cursor: contextReady ? "pointer" : "not-allowed",
              }}
            >
              Wyodrębnij wymagania
            </button>
          </div>
        )}

        {/* No search results */}
        {!loading && requirements.length > 0 && filtered.length === 0 && (
          <p
            className="text-buddy-text-faint text-center"
            style={{ fontSize: 12, paddingTop: 40 }}
          >
            Brak wymagań pasujących do wyszukiwania.
          </p>
        )}

        {/* Grouped requirement cards */}
        {!loading && groups.length > 0 && (
          <div className="flex flex-col gap-3">
            {groups.map(([key, items]) => (
              <ModuleGroup
                key={key}
                label={key}
                items={items}
                onMarkReviewed={onMarkReviewed}
                currentContextId={currentContextId}
                contexts={contexts}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
