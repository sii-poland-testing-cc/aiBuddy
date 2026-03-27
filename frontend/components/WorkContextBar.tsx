"use client";

import { useState, useRef, useEffect } from "react";
import type { WorkContext } from "../lib/useWorkContext";
import WorkContextPanel, { type ItemCounts } from "./WorkContextPanel";

// ── Status badge ───────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, string> = {
  draft:            "text-buddy-text-dim bg-buddy-border/60 border-buddy-border",
  active:           "text-blue-400 bg-blue-400/10 border-blue-400/30",
  ready:            "text-buddy-gold bg-buddy-gold/10 border-buddy-gold/30",
  promoted:         "text-buddy-success bg-buddy-success/10 border-buddy-success/30",
  archived:         "text-buddy-text-faint bg-transparent border-buddy-border/40 line-through",
  conflict_pending: "text-buddy-error bg-buddy-error/10 border-buddy-error/30",
};

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_STYLES[status] ?? STATUS_STYLES.draft;
  return (
    <span
      className={`inline-flex items-center border font-mono ${cls}`}
      style={{ padding: "1px 6px", borderRadius: 3, fontSize: 10, letterSpacing: "0.04em" }}
    >
      {status}
    </span>
  );
}

// ── Breadcrumb helpers ─────────────────────────────────────────────────────────

/** Build ordered chain [domain, epic?, story?] from flat contexts + currentId */
function buildBreadcrumb(
  contexts: WorkContext[],
  currentContextId: string | null,
): WorkContext[] {
  if (!currentContextId) {
    // Domain level — show the first non-archived domain (or all domains = 1 item)
    const domain = contexts.find((c) => c.level === "domain" && c.status !== "archived");
    return domain ? [domain] : [];
  }
  const byId = new Map(contexts.map((c) => [c.id, c]));
  const chain: WorkContext[] = [];
  let cur = byId.get(currentContextId);
  while (cur) {
    chain.unshift(cur);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return chain;
}

// ── Props ──────────────────────────────────────────────────────────────────────

export interface WorkContextBarProps {
  projectId: string;
  contexts: WorkContext[];
  currentContextId: string | null;
  onContextChange: (id: string | null) => void;
  createContext: (level: "epic" | "story", name: string, parentId: string, description?: string) => Promise<WorkContext>;
  createDomain: (name: string, description?: string) => Promise<WorkContext>;
  updateContext: (id: string, patch: { name?: string; description?: string; status?: string }) => Promise<WorkContext>;
  archiveContext: (id: string) => Promise<void>;
  loading?: boolean;
  itemCounts?: Record<string, ItemCounts>;
  pendingConflicts?: number;
  onOpenConflicts?: () => void;
  onPromote?: (ctx: WorkContext) => void;
  isArchiveView?: boolean;
}

export type { ItemCounts };

// ── Component ──────────────────────────────────────────────────────────────────

export default function WorkContextBar({
  projectId,
  contexts,
  currentContextId,
  onContextChange,
  createContext,
  createDomain,
  updateContext,
  archiveContext,
  loading = false,
  itemCounts,
  pendingConflicts,
  onOpenConflicts,
  onPromote,
  isArchiveView = false,
}: WorkContextBarProps) {
  const [panelOpen, setPanelOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Close panel on click-outside
  useEffect(() => {
    if (!panelOpen) return;
    function onDown(e: MouseEvent) {
      if (
        panelRef.current && !panelRef.current.contains(e.target as Node) &&
        buttonRef.current && !buttonRef.current.contains(e.target as Node)
      ) {
        setPanelOpen(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [panelOpen]);

  // Close panel on Escape
  useEffect(() => {
    if (!panelOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setPanelOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [panelOpen]);

  const breadcrumb = buildBreadcrumb(contexts, currentContextId);
  const currentCtx = currentContextId ? contexts.find((c) => c.id === currentContextId) : null;

  return (
    <div
      data-testid="work-context-bar"
      className="fixed left-0 right-0 bg-buddy-surface border-b border-buddy-border flex items-center px-4 gap-2"
      style={{ top: 48, height: 36, zIndex: 90 }}
    >
      {/* ── Breadcrumb ── */}
      <div className="flex items-center gap-1 flex-1 min-w-0 overflow-hidden">
        {loading && contexts.length === 0 ? (
          <span className="text-buddy-text-faint" style={{ fontSize: 11 }}>Loading…</span>
        ) : breadcrumb.length === 0 ? (
          <span className="text-buddy-text-faint" style={{ fontSize: 11 }}>No context</span>
        ) : (
          breadcrumb.map((ctx, i) => {
            const isLast = i === breadcrumb.length - 1;
            // Clicking a segment navigates there:
            // domain → null (domain view = no filter), epic/story → their id
            const targetId = ctx.level === "domain" ? null : ctx.id;
            return (
              <span key={ctx.id} className="flex items-center gap-1 min-w-0">
                {i > 0 && (
                  <span className="text-buddy-text-faint flex-shrink-0" style={{ fontSize: 10 }}>›</span>
                )}
                <button
                  data-testid={`breadcrumb-${ctx.level}`}
                  onClick={() => onContextChange(targetId)}
                  className={`truncate transition-colors ${
                    isLast
                      ? "text-buddy-text font-medium"
                      : "text-buddy-text-muted hover:text-buddy-text"
                  }`}
                  style={{ fontSize: 11, maxWidth: 160 }}
                  title={ctx.name}
                >
                  {ctx.name}
                </button>
              </span>
            );
          })
        )}
      </div>

      {/* ── Status badge for current context ── */}
      {currentCtx && (
        <StatusBadge status={currentCtx.status} />
      )}

      {/* ── Archive view label ── */}
      {isArchiveView && (
        <span
          data-testid="archive-view-label"
          className="inline-flex items-center text-buddy-text-faint flex-shrink-0"
          style={{ fontSize: 10, letterSpacing: "0.04em" }}
        >
          Archive view
        </span>
      )}

      {/* ── Lifecycle action button ── */}
      {currentCtx && (() => {
        const parentCtx = currentCtx.parent_id
          ? contexts.find((c) => c.id === currentCtx.parent_id)
          : null;
        const parentName = parentCtx?.name ?? "parent";

        switch (currentCtx.status) {
          case "draft":
            return (
              <button
                data-testid="lifecycle-action-btn"
                onClick={() => updateContext(currentCtx.id, { status: "active" })}
                className="flex items-center gap-1 border border-blue-400/40 text-blue-400 bg-blue-400/10 hover:bg-blue-400/20 rounded-[4px] transition-colors flex-shrink-0"
                style={{ padding: "3px 8px", fontSize: 11 }}
              >
                Activate
              </button>
            );
          case "active":
            return (
              <button
                data-testid="lifecycle-action-btn"
                onClick={() => updateContext(currentCtx.id, { status: "ready" })}
                className="flex items-center gap-1 border border-buddy-gold/40 text-buddy-gold bg-buddy-gold/10 hover:bg-buddy-gold/20 rounded-[4px] transition-colors flex-shrink-0"
                style={{ padding: "3px 8px", fontSize: 11 }}
              >
                Mark as Ready ✓
              </button>
            );
          case "ready":
            return (
              <button
                data-testid="lifecycle-action-btn"
                onClick={() => onPromote?.(currentCtx)}
                className="flex items-center gap-1 border border-buddy-success/40 text-buddy-success bg-buddy-success/10 hover:bg-buddy-success/20 rounded-[4px] transition-colors flex-shrink-0"
                style={{ padding: "3px 8px", fontSize: 11 }}
              >
                Promote ↑ to {parentName}
              </button>
            );
          case "promoted":
            return (
              <span
                data-testid="lifecycle-action-btn"
                className="inline-flex items-center gap-1 border border-buddy-success/30 text-buddy-success bg-buddy-success/10 rounded-[4px] flex-shrink-0"
                style={{ padding: "3px 8px", fontSize: 11 }}
              >
                ✓ Promoted
              </span>
            );
          case "conflict_pending":
            return (
              <button
                data-testid="lifecycle-action-btn"
                onClick={onOpenConflicts}
                className="flex items-center gap-1 border border-buddy-error/40 text-buddy-error bg-buddy-error/10 hover:bg-buddy-error/20 rounded-[4px] transition-colors flex-shrink-0"
                style={{ padding: "3px 8px", fontSize: 11 }}
              >
                Resolve Conflicts{(pendingConflicts ?? 0) > 0 ? ` (${pendingConflicts})` : ""}
              </button>
            );
          default:
            return null;
        }
      })()}

      {/* ── Conflict badge ── */}
      {(pendingConflicts ?? 0) > 0 && (
        <button
          data-testid="conflict-badge-btn"
          onClick={onOpenConflicts}
          className="flex items-center gap-1 border border-buddy-error/40 text-buddy-error bg-buddy-error/10 hover:bg-buddy-error/20 rounded-[4px] transition-colors flex-shrink-0"
          style={{ padding: "3px 8px", fontSize: 11 }}
        >
          ⚠ {pendingConflicts} conflict{pendingConflicts !== 1 ? "s" : ""}
        </button>
      )}

      {/* ── Manage button ── */}
      <div className="relative flex-shrink-0">
        <button
          ref={buttonRef}
          data-testid="manage-contexts-btn"
          onClick={() => setPanelOpen((o) => !o)}
          className={`flex items-center gap-1 border transition-colors rounded-[4px] ${
            panelOpen
              ? "bg-buddy-gold/15 border-buddy-gold/40 text-buddy-gold"
              : "border-buddy-border text-buddy-text-dim hover:border-buddy-border-dark hover:text-buddy-text-muted"
          }`}
          style={{ padding: "3px 8px", fontSize: 11 }}
        >
          Manage
          <span style={{ fontSize: 9 }}>{panelOpen ? "▲" : "▾"}</span>
        </button>

        {/* ── Panel ── */}
        {panelOpen && (
          <div ref={panelRef} data-testid="work-context-panel-container">
            <WorkContextPanel
              projectId={projectId}
              contexts={contexts}
              currentContextId={currentContextId}
              onSelect={(id) => { onContextChange(id); setPanelOpen(false); }}
              createContext={createContext}
              createDomain={createDomain}
              updateContext={updateContext}
              archiveContext={archiveContext}
              onPromote={onPromote}
              itemCounts={itemCounts}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export { StatusBadge };
