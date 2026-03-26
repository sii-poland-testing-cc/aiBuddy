"use client";

import { useState } from "react";
import type { WorkContext } from "../lib/useWorkContext";
import { StatusBadge } from "./WorkContextBar";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface ItemCounts {
  reqs: number;
  audits: number;
}

interface WorkContextNode extends WorkContext {
  children: WorkContextNode[];
}

type DialogState =
  | { kind: "none" }
  | { kind: "create"; level: "epic" | "story"; parentId: string; parentName: string }
  | { kind: "create_domain" }
  | { kind: "edit"; ctx: WorkContext };

// ── Tree builder ───────────────────────────────────────────────────────────────

function buildTree(contexts: WorkContext[]): WorkContextNode[] {
  const byId = new Map<string, WorkContextNode>();
  for (const c of contexts) byId.set(c.id, { ...c, children: [] });
  const roots: WorkContextNode[] = [];
  for (const node of byId.values()) {
    if (node.parent_id && byId.has(node.parent_id)) {
      byId.get(node.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function ContextNode({
  node,
  depth,
  currentContextId,
  onSelect,
  onAddChild,
  onEdit,
  onMarkReady,
  onArchive,
  onPromote,
  itemCounts,
}: {
  node: WorkContextNode;
  depth: number;
  currentContextId: string | null;
  onSelect: (id: string | null) => void;
  onAddChild: (level: "epic" | "story", parentId: string, parentName: string) => void;
  onEdit: (ctx: WorkContext) => void;
  onMarkReady: (ctx: WorkContext) => void;
  onArchive: (ctx: WorkContext) => void;
  onPromote?: (ctx: WorkContext) => void;
  itemCounts?: Record<string, ItemCounts>;
}) {
  const isActive = node.level === "domain"
    ? currentContextId === null
    : currentContextId === node.id;
  const isArchived = node.status === "archived";
  const canMarkReady = node.status === "active";
  const canAddEpic = node.level === "domain" && !isArchived;
  const canAddStory = node.level === "epic" && !isArchived;

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 group rounded transition-colors ${
          isActive
            ? "bg-buddy-gold/10 border border-buddy-gold/30"
            : "hover:bg-buddy-elevated border border-transparent"
        } ${isArchived ? "opacity-40" : ""}`}
        style={{ paddingLeft: 8 + depth * 14, paddingRight: 6, paddingTop: 4, paddingBottom: 4, marginBottom: 1 }}
      >
        {/* Level indicator dot */}
        <span
          className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            node.level === "domain" ? "bg-buddy-gold/60" :
            node.level === "epic"   ? "bg-blue-400/60" :
                                      "bg-buddy-success/60"
          }`}
        />

        {/* Name — clickable */}
        <button
          data-testid={`ctx-node-${node.id}`}
          onClick={() => onSelect(node.level === "domain" ? null : node.id)}
          className="flex-1 text-left truncate"
          style={{ fontSize: 11 }}
          title={node.name}
        >
          <span className={isArchived ? "line-through" : ""}>{node.name}</span>
        </button>

        {/* Status badge */}
        <StatusBadge status={node.status} />

        {/* Item count chips */}
        {(() => {
          const counts = itemCounts?.[node.id];
          if (!counts) return null;
          const parts = [];
          if (counts.reqs > 0) parts.push(`${counts.reqs}r`);
          if (counts.audits > 0) parts.push(`${counts.audits}a`);
          if (!parts.length) return null;
          return (
            <span className="text-buddy-text-faint font-mono flex-shrink-0" style={{ fontSize: 9 }}>
              [{parts.join(" ")}]
            </span>
          );
        })()}

        {/* Actions — shown on hover */}
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
          {canMarkReady && (
            <button
              data-testid={`ctx-ready-${node.id}`}
              onClick={(e) => { e.stopPropagation(); onMarkReady(node); }}
              className="text-buddy-gold hover:text-buddy-gold-light transition-colors"
              style={{ fontSize: 10, padding: "1px 4px" }}
              title="Mark as Ready"
            >
              ✓
            </button>
          )}
          {node.status === "ready" && !isArchived && onPromote && (
            <button
              data-testid={`ctx-promote-${node.id}`}
              onClick={(e) => { e.stopPropagation(); onPromote(node); }}
              className="text-buddy-success hover:text-buddy-success/80 transition-colors font-medium"
              style={{ fontSize: 10, padding: "1px 4px" }}
              title="Promote to parent"
            >
              ↑
            </button>
          )}
          {!isArchived && (
            <button
              data-testid={`ctx-edit-${node.id}`}
              onClick={(e) => { e.stopPropagation(); onEdit(node); }}
              className="text-buddy-text-dim hover:text-buddy-text-muted transition-colors"
              style={{ fontSize: 10, padding: "1px 4px" }}
              title="Edit"
            >
              ✎
            </button>
          )}
          {!isArchived && (
            <button
              data-testid={`ctx-archive-${node.id}`}
              onClick={(e) => { e.stopPropagation(); onArchive(node); }}
              className="text-buddy-text-dim hover:text-buddy-error transition-colors"
              style={{ fontSize: 10, padding: "1px 4px" }}
              title="Archive"
            >
              ×
            </button>
          )}
          {canAddEpic && (
            <button
              data-testid={`ctx-add-epic-${node.id}`}
              onClick={(e) => { e.stopPropagation(); onAddChild("epic", node.id, node.name); }}
              className="text-buddy-text-dim hover:text-blue-400 transition-colors"
              style={{ fontSize: 10, padding: "1px 4px" }}
              title="Add Epic"
            >
              +Epic
            </button>
          )}
          {canAddStory && (
            <button
              data-testid={`ctx-add-story-${node.id}`}
              onClick={(e) => { e.stopPropagation(); onAddChild("story", node.id, node.name); }}
              className="text-buddy-text-dim hover:text-buddy-success transition-colors"
              style={{ fontSize: 10, padding: "1px 4px" }}
              title="Add Story"
            >
              +Story
            </button>
          )}
        </div>
      </div>

      {/* Children */}
      {node.children.map((child) => (
        <ContextNode
          key={child.id}
          node={child}
          depth={depth + 1}
          currentContextId={currentContextId}
          onSelect={onSelect}
          onAddChild={onAddChild}
          onEdit={onEdit}
          onMarkReady={onMarkReady}
          onArchive={onArchive}
          onPromote={onPromote}
          itemCounts={itemCounts}
        />
      ))}
    </div>
  );
}

// ── Dialog ─────────────────────────────────────────────────────────────────────

function ContextDialog({
  dialog,
  onSubmit,
  onClose,
  error,
  submitting,
}: {
  dialog: DialogState;
  onSubmit: (name: string, description: string) => void;
  onClose: () => void;
  error: string | null;
  submitting: boolean;
}) {
  const [name, setName] = useState(
    dialog.kind === "edit" ? dialog.ctx.name : ""
  );
  const [desc, setDesc] = useState(
    dialog.kind === "edit" ? (dialog.ctx.description ?? "") : ""
  );

  const title =
    dialog.kind === "create_domain"  ? "New Domain" :
    dialog.kind === "create" && dialog.level === "epic"  ? `New Epic under "${dialog.parentName}"` :
    dialog.kind === "create" && dialog.level === "story" ? `New Story under "${dialog.parentName}"` :
    dialog.kind === "edit"           ? `Edit "${dialog.ctx.name}"` : "";

  return (
    <div
      className="fixed inset-0 flex items-center justify-center"
      style={{ zIndex: 200 }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Dialog */}
      <div
        data-testid="ctx-dialog"
        className="relative bg-buddy-surface2 border border-buddy-border rounded-[8px] shadow-xl animate-fade-up"
        style={{ width: 360, padding: 20 }}
      >
        <h3 className="text-buddy-text font-semibold" style={{ fontSize: 13, marginBottom: 12 }}>{title}</h3>

        <div style={{ marginBottom: 10 }}>
          <label className="text-buddy-text-muted block" style={{ fontSize: 11, marginBottom: 4 }}>
            Name <span className="text-buddy-error">*</span>
          </label>
          <input
            data-testid="ctx-dialog-name"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !submitting && name.trim() && onSubmit(name.trim(), desc)}
            className="w-full border border-buddy-border rounded-[4px] focus:border-buddy-gold focus:outline-none"
            style={{ padding: "5px 8px", fontSize: 12 }}
            placeholder="Name…"
          />
        </div>

        <div style={{ marginBottom: 14 }}>
          <label className="text-buddy-text-muted block" style={{ fontSize: 11, marginBottom: 4 }}>
            Description <span className="text-buddy-text-faint">(optional)</span>
          </label>
          <textarea
            data-testid="ctx-dialog-desc"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            className="w-full border border-buddy-border rounded-[4px] focus:border-buddy-gold focus:outline-none"
            style={{ padding: "5px 8px", fontSize: 12, minHeight: 60, resize: "vertical" }}
            placeholder="Description…"
          />
        </div>

        {error && (
          <p className="text-buddy-error" style={{ fontSize: 11, marginBottom: 10 }}>{error}</p>
        )}

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="text-buddy-text-muted hover:text-buddy-text border border-buddy-border rounded-[4px] transition-colors"
            style={{ padding: "4px 12px", fontSize: 11 }}
          >
            Cancel
          </button>
          <button
            data-testid="ctx-dialog-submit"
            disabled={!name.trim() || submitting}
            onClick={() => onSubmit(name.trim(), desc)}
            className="bg-buddy-gold/15 border border-buddy-gold/40 text-buddy-gold hover:bg-buddy-gold/25 disabled:opacity-40 disabled:cursor-not-allowed rounded-[4px] transition-colors font-medium"
            style={{ padding: "4px 12px", fontSize: 11 }}
          >
            {submitting ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main panel component ───────────────────────────────────────────────────────

export interface WorkContextPanelProps {
  projectId: string;
  contexts: WorkContext[];
  currentContextId: string | null;
  onSelect: (id: string | null) => void;
  createContext: (level: "epic" | "story", name: string, parentId: string, description?: string) => Promise<WorkContext>;
  createDomain: (name: string, description?: string) => Promise<WorkContext>;
  updateContext: (id: string, patch: { name?: string; description?: string; status?: string }) => Promise<WorkContext>;
  archiveContext: (id: string) => Promise<void>;
  onPromote?: (ctx: WorkContext) => void;
  itemCounts?: Record<string, ItemCounts>;
}

export default function WorkContextPanel({
  projectId: _projectId,
  contexts,
  currentContextId,
  onSelect,
  createContext,
  createDomain,
  updateContext,
  archiveContext,
  onPromote,
  itemCounts,
}: WorkContextPanelProps) {
  const [dialog, setDialog] = useState<DialogState>({ kind: "none" });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const tree = buildTree(contexts);

  const openCreate = (level: "epic" | "story", parentId: string, parentName: string) => {
    setError(null);
    setDialog({ kind: "create", level, parentId, parentName });
  };

  const openEdit = (ctx: WorkContext) => {
    setError(null);
    setDialog({ kind: "edit", ctx });
  };

  const openCreateDomain = () => {
    setError(null);
    setDialog({ kind: "create_domain" });
  };

  const handleMarkReady = async (ctx: WorkContext) => {
    try {
      await updateContext(ctx.id, { status: "ready" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    }
  };

  const handleArchive = async (ctx: WorkContext) => {
    try {
      await archiveContext(ctx.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to archive context");
    }
  };

  const handleDialogSubmit = async (name: string, description: string) => {
    setError(null);
    setSubmitting(true);
    try {
      if (dialog.kind === "create_domain") {
        await createDomain(name, description || undefined);
      } else if (dialog.kind === "create") {
        await createContext(dialog.level, name, dialog.parentId, description || undefined);
      } else if (dialog.kind === "edit") {
        await updateContext(dialog.ctx.id, { name, description: description || undefined });
      }
      setDialog({ kind: "none" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "An error occurred");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      {/* Panel */}
      <div
        data-testid="work-context-panel"
        className="absolute bg-buddy-surface2 border border-buddy-border rounded-[6px] shadow-xl overflow-hidden"
        style={{ top: "calc(100% + 4px)", right: 0, width: 320, maxHeight: 420, zIndex: 96 }}
      >
        {/* Header */}
        <div
          className="border-b border-buddy-border flex items-center justify-between"
          style={{ padding: "8px 12px" }}
        >
          <span className="text-buddy-text-muted font-semibold uppercase tracking-widest" style={{ fontSize: 10 }}>
            Work Contexts
          </span>
          <span className="text-buddy-text-faint" style={{ fontSize: 10 }}>
            {contexts.filter((c) => c.status !== "archived").length} active
          </span>
        </div>

        {/* Tree */}
        <div className="overflow-y-auto" style={{ maxHeight: 320, padding: "6px 6px" }}>
          {tree.length === 0 ? (
            <p className="text-buddy-text-faint text-center" style={{ fontSize: 11, padding: "16px 0" }}>
              No contexts yet
            </p>
          ) : (
            tree.map((node) => (
              <ContextNode
                key={node.id}
                node={node}
                depth={0}
                currentContextId={currentContextId}
                onSelect={onSelect}
                onAddChild={openCreate}
                onEdit={openEdit}
                onMarkReady={handleMarkReady}
                onArchive={handleArchive}
                onPromote={onPromote}
                itemCounts={itemCounts}
              />
            ))
          )}
        </div>

        {/* Error */}
        {error && (
          <div
            className="border-t border-buddy-error/20 text-buddy-error"
            style={{ padding: "6px 12px", fontSize: 11 }}
          >
            {error}
          </div>
        )}

        {/* Footer — Create Domain */}
        <div className="border-t border-buddy-border" style={{ padding: "6px 8px" }}>
          <button
            data-testid="create-domain-btn"
            onClick={openCreateDomain}
            className="w-full text-center border border-dashed border-buddy-border text-buddy-text-dim hover:border-buddy-gold/40 hover:text-buddy-gold rounded-[4px] transition-colors"
            style={{ padding: "5px 8px", fontSize: 11 }}
          >
            + New Domain
          </button>
        </div>
      </div>

      {/* Dialog (rendered outside the panel scroll area) */}
      {dialog.kind !== "none" && (
        <ContextDialog
          dialog={dialog}
          onSubmit={handleDialogSubmit}
          onClose={() => { setDialog({ kind: "none" }); setError(null); }}
          error={error}
          submitting={submitting}
        />
      )}
    </>
  );
}
