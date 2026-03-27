"use client";
import { useState, useEffect, useMemo } from "react";
import { useConflicts, type Conflict, type ResolutionType } from "../lib/useConflicts";

// ── Constants ──────────────────────────────────────────────────────────────────

const TYPE_ICON: Record<string, string> = {
  requirement: "📋",
  graph_node: "⬡",
  graph_edge: "⤳",
  glossary_term: "📖",
};

const TYPE_LABEL: Record<string, string> = {
  requirement: "REQ",
  graph_node: "NODE",
  graph_edge: "EDGE",
  glossary_term: "TERM",
};

const FIELDS: Record<string, string[]> = {
  requirement: ["title", "description", "external_id"],
  graph_node: ["label", "type", "description"],
  graph_edge: ["source", "target", "label"],
  glossary_term: ["term", "definition"],
};

const ARTIFACT_TYPES = ["requirement", "graph_node", "graph_edge", "glossary_term"];

// ── Word diff helper ───────────────────────────────────────────────────────────

function computeWordDiff(
  oldText: string,
  newText: string,
): Array<{ word: string; type: "same" | "removed" | "added" }> {
  const oldWords = oldText.split(/(\s+)/);
  const newWords = newText.split(/(\s+)/);
  const m = oldWords.length;
  const n = newWords.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (oldWords[i] === newWords[j]) dp[i][j] = 1 + dp[i + 1][j + 1];
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const result: Array<{ word: string; type: "same" | "removed" | "added" }> = [];
  let i = 0;
  let j = 0;
  while (i < m || j < n) {
    if (i < m && j < n && oldWords[i] === newWords[j]) {
      result.push({ word: oldWords[i], type: "same" });
      i++;
      j++;
    } else if (j < n && (i >= m || dp[i][j + 1] >= dp[i + 1][j])) {
      result.push({ word: newWords[j], type: "added" });
      j++;
    } else {
      result.push({ word: oldWords[i], type: "removed" });
      i++;
    }
  }
  return result;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function WordDiffText({ oldText, newText }: { oldText: string; newText: string }) {
  const diff = computeWordDiff(String(oldText ?? ""), String(newText ?? ""));
  return (
    <span>
      {diff.map((d, idx) => {
        if (d.type === "same") {
          return (
            <span key={idx} style={{ color: "#a09078" }}>
              {d.word}
            </span>
          );
        }
        if (d.type === "removed") {
          return (
            <span
              key={idx}
              style={{
                background: "rgba(200,58,58,0.2)",
                color: "#ff8080",
                textDecoration: "line-through",
              }}
            >
              {d.word}
            </span>
          );
        }
        return (
          <span
            key={idx}
            style={{ background: "rgba(74,158,107,0.2)", color: "#80e0a0" }}
          >
            {d.word}
          </span>
        );
      })}
    </span>
  );
}

function FieldValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span style={{ color: "#6a5a48", fontStyle: "italic" }}>null</span>;
  }
  if (Array.isArray(value)) {
    return <span>{value.join(", ")}</span>;
  }
  return <span>{String(value)}</span>;
}

interface ConflictDiffPanelProps {
  conflict: Conflict;
  noteText: string;
  onNoteChange: (v: string) => void;
  editMode: boolean;
  editValue: string;
  onEditValueChange: (v: string) => void;
  onToggleEditMode: () => void;
  onResolve: (resolution: ResolutionType, resolvedValue?: Record<string, unknown> | null) => void;
  resolving: boolean;
}

function ConflictDiffPanel({
  conflict,
  noteText,
  onNoteChange,
  editMode,
  editValue,
  onEditValueChange,
  onToggleEditMode,
  onResolve,
  resolving,
}: ConflictDiffPanelProps) {
  const fields = FIELDS[conflict.artifact_type] ?? Object.keys(conflict.existing_value ?? {});

  const handleSaveMerged = () => {
    try {
      const parsed = JSON.parse(editValue) as Record<string, unknown>;
      onResolve("edited", parsed);
    } catch {
      // JSON parse error — user should fix it
    }
  };

  return (
    <div
      data-testid="conflict-diff-panel"
      className="flex flex-col h-full overflow-hidden"
      style={{ padding: "12px 16px" }}
    >
      {/* Conflict reason */}
      <div
        className="text-buddy-text-muted border border-buddy-border/50 rounded-[4px]"
        style={{ padding: "6px 10px", fontSize: 11, marginBottom: 12, background: "rgba(42,37,32,0.6)" }}
      >
        <span className="text-buddy-text-dim" style={{ fontSize: 10, marginRight: 6 }}>Reason:</span>
        {conflict.conflict_reason}
      </div>

      {/* Side-by-side diff */}
      <div className="flex gap-2 flex-1 overflow-hidden" style={{ marginBottom: 12 }}>
        {/* Existing (current) */}
        <div
          data-testid="existing-panel"
          className="flex-1 border border-buddy-border rounded-[4px] overflow-auto"
          style={{ minWidth: 0 }}
        >
          <div
            className="border-b border-buddy-border sticky top-0 bg-buddy-elevated"
            style={{ padding: "5px 10px", fontSize: 10, color: "#8a7a68" }}
          >
            Current ({conflict.target_context_name ?? "target"}{conflict.existing_version != null ? `, v${conflict.existing_version}` : ""})
          </div>
          <div style={{ padding: "8px 10px" }}>
            {fields.map((field) => {
              const existingVal = conflict.existing_value?.[field];
              const incomingVal = conflict.incoming_value?.[field];
              const hasChange =
                String(existingVal ?? "") !== String(incomingVal ?? "");
              return (
                <div key={field} style={{ marginBottom: 8 }}>
                  <div
                    className="text-buddy-text-dim"
                    style={{ fontSize: 9, marginBottom: 2, textTransform: "uppercase" }}
                  >
                    {field}
                  </div>
                  <div style={{ fontSize: 11, color: hasChange ? "#ff8080" : "#a09078" }}>
                    {hasChange ? (
                      <WordDiffText
                        oldText={String(existingVal ?? "")}
                        newText={String(incomingVal ?? "")}
                      />
                    ) : (
                      <FieldValue value={existingVal} />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Incoming */}
        <div
          data-testid="incoming-panel"
          className="flex-1 border border-buddy-border rounded-[4px] overflow-auto"
          style={{ minWidth: 0 }}
        >
          <div
            className="border-b border-buddy-border sticky top-0 bg-buddy-elevated"
            style={{ padding: "5px 10px", fontSize: 10, color: "#8a7a68" }}
          >
            Incoming ({conflict.source_context_name ?? "source"}{conflict.incoming_version != null ? `, v${conflict.incoming_version}` : ""})
          </div>
          <div style={{ padding: "8px 10px" }}>
            {fields.map((field) => {
              const incomingVal = conflict.incoming_value?.[field];
              return (
                <div key={field} style={{ marginBottom: 8 }}>
                  <div
                    className="text-buddy-text-dim"
                    style={{ fontSize: 9, marginBottom: 2, textTransform: "uppercase" }}
                  >
                    {field}
                  </div>
                  <div style={{ fontSize: 11, color: "#80e0a0" }}>
                    <FieldValue value={incomingVal} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Edit & Merge textarea */}
      {editMode && (
        <div style={{ marginBottom: 10 }}>
          <div
            data-testid="sibling-note"
            className="border border-buddy-gold/20 rounded-[4px] text-buddy-text-muted"
            style={{ padding: "6px 10px", fontSize: 10, marginBottom: 8, background: "rgba(200,144,42,0.06)" }}
          >
            This will create a new version in <strong className="text-buddy-text-dim">{conflict.target_context_name ?? "target"}</strong>.
            The original in <strong className="text-buddy-text-dim">{conflict.source_context_name ?? "source"}</strong> remains unchanged.
          </div>
          <div className="text-buddy-text-muted" style={{ fontSize: 10, marginBottom: 4 }}>
            Edit merged value (JSON):
          </div>
          <textarea
            data-testid="merge-edit-textarea"
            value={editValue}
            onChange={(e) => onEditValueChange(e.target.value)}
            className="w-full border border-buddy-gold/40 rounded-[4px] focus:border-buddy-gold focus:outline-none font-mono"
            style={{ padding: "6px 8px", fontSize: 11, minHeight: 80, resize: "vertical" }}
          />
        </div>
      )}

      {/* Note field */}
      <div style={{ marginBottom: 10 }}>
        <input
          value={noteText}
          onChange={(e) => onNoteChange(e.target.value)}
          className="w-full border border-buddy-border rounded-[4px] focus:border-buddy-gold/60 focus:outline-none"
          style={{ padding: "5px 8px", fontSize: 11 }}
          placeholder="Optional note…"
        />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          data-testid="resolve-keep-btn"
          disabled={resolving}
          onClick={() => onResolve("keep_old")}
          className="border border-blue-400/40 text-blue-400 bg-blue-400/10 hover:bg-blue-400/20 disabled:opacity-40 disabled:cursor-not-allowed rounded-[4px] transition-colors"
          style={{ padding: "5px 12px", fontSize: 11 }}
        >
          Keep Current
        </button>
        <button
          data-testid="resolve-defer-btn"
          disabled={resolving}
          onClick={() => onResolve("defer")}
          className="border border-buddy-border text-buddy-text-muted hover:text-buddy-text disabled:opacity-40 disabled:cursor-not-allowed rounded-[4px] transition-colors"
          style={{ padding: "5px 12px", fontSize: 11 }}
        >
          Defer
        </button>
        <button
          data-testid="resolve-accept-btn"
          disabled={resolving}
          onClick={() => onResolve("accept_new")}
          className="border border-buddy-success/40 text-buddy-success bg-buddy-success/10 hover:bg-buddy-success/20 disabled:opacity-40 disabled:cursor-not-allowed rounded-[4px] transition-colors"
          style={{ padding: "5px 12px", fontSize: 11 }}
        >
          Accept Incoming
        </button>

        {editMode ? (
          <>
            <button
              onClick={handleSaveMerged}
              disabled={resolving}
              className="border border-buddy-gold/40 text-buddy-gold bg-buddy-gold/10 hover:bg-buddy-gold/20 disabled:opacity-40 disabled:cursor-not-allowed rounded-[4px] transition-colors ml-auto"
              style={{ padding: "5px 12px", fontSize: 11 }}
            >
              Save Merged Version
            </button>
            <button
              onClick={onToggleEditMode}
              className="text-buddy-text-muted hover:text-buddy-text transition-colors"
              style={{ fontSize: 11 }}
            >
              Cancel Edit
            </button>
          </>
        ) : (
          <button
            data-testid="resolve-edit-btn"
            onClick={onToggleEditMode}
            className="border border-buddy-gold/40 text-buddy-gold bg-buddy-gold/10 hover:bg-buddy-gold/20 rounded-[4px] transition-colors ml-auto"
            style={{ padding: "5px 12px", fontSize: 11 }}
          >
            Edit &amp; Merge
          </button>
        )}
      </div>
    </div>
  );
}

// ── Props ──────────────────────────────────────────────────────────────────────

interface ConflictResolutionProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
  initialContextId?: string | null;
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function ConflictResolution({
  open,
  onClose,
  projectId,
  initialContextId,
}: ConflictResolutionProps) {
  const { conflicts, loading, pendingCount, refresh, resolve } = useConflicts(projectId);
  const [selectedConflictId, setSelectedConflictId] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string | null>(null);
  const [noteText, setNoteText] = useState("");
  const [editValue, setEditValue] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [siblingInfo, setSiblingInfo] = useState<{
    itemLabel: string;
    targetName: string;
    sourceName: string;
  } | null>(null);

  // Refresh when opened
  useEffect(() => {
    if (open) {
      refresh(undefined, initialContextId ?? undefined);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const filteredConflicts = useMemo(() => {
    if (!filterType) return conflicts;
    return conflicts.filter((c) => c.artifact_type === filterType);
  }, [conflicts, filterType]);

  const pendingConflicts = useMemo(
    () => filteredConflicts.filter((c) => c.status === "pending"),
    [filteredConflicts],
  );
  const deferredConflicts = useMemo(
    () => filteredConflicts.filter((c) => c.status === "deferred"),
    [filteredConflicts],
  );

  const selectedConflict = useMemo(
    () => conflicts.find((c) => c.id === selectedConflictId) ?? null,
    [conflicts, selectedConflictId],
  );

  const handleSelectConflict = (c: Conflict) => {
    setSelectedConflictId(c.id);
    setNoteText("");
    setEditMode(false);
    setEditValue(JSON.stringify(c.incoming_value, null, 2));
    setResolveError(null);
  };

  const handleToggleEditMode = () => {
    if (!editMode && selectedConflict) {
      setEditValue(JSON.stringify(selectedConflict.incoming_value, null, 2));
    }
    setEditMode((v) => !v);
  };

  const handleResolve = async (
    resolution: ResolutionType,
    resolvedValue?: Record<string, unknown> | null,
  ) => {
    if (!selectedConflict) return;
    setResolving(true);
    setResolveError(null);
    try {
      await resolve(selectedConflict.id, resolution, resolvedValue, noteText || null);
      // Show sibling info after Edit & Merge resolution
      if (resolution === "edited") {
        const itemLabel =
          (selectedConflict.incoming_value?.title as string) ??
          (selectedConflict.incoming_value?.label as string) ??
          (selectedConflict.incoming_value?.term as string) ??
          selectedConflict.artifact_item_id;
        setSiblingInfo({
          itemLabel,
          targetName: selectedConflict.target_context_name ?? "target",
          sourceName: selectedConflict.source_context_name ?? "source",
        });
      } else {
        setSiblingInfo(null);
      }
      setSelectedConflictId(null);
      setNoteText("");
      setEditMode(false);
    } catch (e) {
      setResolveError(e instanceof Error ? e.message : "Resolution failed");
    } finally {
      setResolving(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 flex items-center justify-center"
      style={{ zIndex: 400 }}
    >
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div
        data-testid="conflict-resolution-panel"
        className="relative bg-buddy-surface border border-buddy-border rounded-[8px] shadow-2xl flex flex-col overflow-hidden"
        style={{ width: "90vw", maxWidth: 960, height: "80vh" }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between border-b border-buddy-border flex-shrink-0"
          style={{ padding: "10px 16px" }}
        >
          <div className="flex items-center gap-3">
            <span className="font-semibold text-buddy-text" style={{ fontSize: 13 }}>
              ⚠ Conflict Queue
            </span>
            <span
              data-testid="conflict-count"
              className="text-buddy-error font-mono"
              style={{ fontSize: 11 }}
            >
              {pendingCount}
            </span>
            <span className="text-buddy-text-muted" style={{ fontSize: 11 }}>
              pending
            </span>
          </div>
          <button
            data-testid="conflict-panel-close-btn"
            onClick={onClose}
            className="text-buddy-text-dim hover:text-buddy-text transition-colors"
            style={{ fontSize: 14 }}
          >
            ✕ Close
          </button>
        </div>

        {/* Body: sidebar + main */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left sidebar */}
          <div
            className="border-r border-buddy-border flex flex-col overflow-hidden flex-shrink-0"
            style={{ width: 250 }}
          >
            {/* Type filter chips */}
            <div
              className="flex flex-wrap gap-1 border-b border-buddy-border"
              style={{ padding: "6px 8px" }}
            >
              <button
                onClick={() => setFilterType(null)}
                className={`border rounded-[3px] transition-colors ${
                  filterType === null
                    ? "border-buddy-gold/50 text-buddy-gold bg-buddy-gold/10"
                    : "border-buddy-border text-buddy-text-dim hover:text-buddy-text-muted"
                }`}
                style={{ padding: "2px 7px", fontSize: 10 }}
              >
                All
              </button>
              {ARTIFACT_TYPES.map((type) => (
                <button
                  key={type}
                  onClick={() => setFilterType(filterType === type ? null : type)}
                  className={`border rounded-[3px] transition-colors ${
                    filterType === type
                      ? "border-buddy-gold/50 text-buddy-gold bg-buddy-gold/10"
                      : "border-buddy-border text-buddy-text-dim hover:text-buddy-text-muted"
                  }`}
                  style={{ padding: "2px 7px", fontSize: 10 }}
                >
                  {TYPE_LABEL[type]}
                </button>
              ))}
            </div>

            {/* Conflict list */}
            <div className="flex-1 overflow-y-auto" style={{ padding: "4px 0" }}>
              {loading && conflicts.length === 0 ? (
                <p
                  className="text-buddy-text-muted text-center"
                  style={{ fontSize: 11, padding: "12px 8px" }}
                >
                  Loading…
                </p>
              ) : pendingConflicts.length === 0 && deferredConflicts.length === 0 ? (
                <div
                  data-testid="conflict-empty-state"
                  className="text-buddy-text-muted text-center"
                  style={{ fontSize: 11, padding: "24px 8px" }}
                >
                  <div style={{ fontSize: 20, marginBottom: 6 }}>✓</div>
                  No conflicts to review
                </div>
              ) : (
                <>
                  {pendingConflicts.length > 0 && (
                    <>
                      <div
                        className="text-buddy-text-faint uppercase tracking-widest"
                        style={{ padding: "4px 10px", fontSize: 9 }}
                      >
                        — pending —
                      </div>
                      {pendingConflicts.map((c) => (
                        <ConflictRow
                          key={c.id}
                          conflict={c}
                          selected={selectedConflictId === c.id}
                          onClick={() => handleSelectConflict(c)}
                        />
                      ))}
                    </>
                  )}
                  {deferredConflicts.length > 0 && (
                    <>
                      <div
                        className="text-buddy-text-faint uppercase tracking-widest"
                        style={{ padding: "4px 10px", fontSize: 9 }}
                      >
                        — deferred —
                      </div>
                      {deferredConflicts.map((c) => (
                        <ConflictRow
                          key={c.id}
                          conflict={c}
                          selected={selectedConflictId === c.id}
                          onClick={() => handleSelectConflict(c)}
                        />
                      ))}
                    </>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Right: diff area */}
          <div className="flex-1 overflow-hidden flex flex-col">
            {resolveError && (
              <div
                className="text-buddy-error border-b border-buddy-error/20 flex-shrink-0"
                style={{ padding: "6px 16px", fontSize: 11, background: "rgba(200,90,58,0.06)" }}
              >
                ⚠ {resolveError}
              </div>
            )}
            {siblingInfo && !selectedConflict && (
              <div
                data-testid="sibling-confirmation"
                className="border-b border-buddy-success/20 flex-shrink-0 flex items-center gap-2"
                style={{ padding: "6px 16px", fontSize: 11, background: "rgba(74,158,107,0.06)", color: "#4a9e6b" }}
              >
                <span>
                  ✓ New version created in &quot;{siblingInfo.targetName}&quot;.
                  Based on &quot;{siblingInfo.itemLabel}&quot; from &quot;{siblingInfo.sourceName}&quot;.
                </span>
                <button
                  onClick={() => setSiblingInfo(null)}
                  className="ml-auto text-buddy-success/60 hover:text-buddy-success transition-colors"
                  style={{ fontSize: 12 }}
                >
                  ✕
                </button>
              </div>
            )}
            {selectedConflict ? (
              <ConflictDiffPanel
                conflict={selectedConflict}
                noteText={noteText}
                onNoteChange={setNoteText}
                editMode={editMode}
                editValue={editValue}
                onEditValueChange={setEditValue}
                onToggleEditMode={handleToggleEditMode}
                onResolve={handleResolve}
                resolving={resolving}
              />
            ) : (
              <div
                className="flex-1 flex items-center justify-center text-buddy-text-muted"
                style={{ fontSize: 12 }}
              >
                Select a conflict to review
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Conflict row ───────────────────────────────────────────────────────────────

function ConflictRow({
  conflict,
  selected,
  onClick,
}: {
  conflict: Conflict;
  selected: boolean;
  onClick: () => void;
}) {
  const icon = TYPE_ICON[conflict.artifact_type] ?? "?";
  const label = TYPE_LABEL[conflict.artifact_type] ?? conflict.artifact_type;
  const itemLabel =
    (conflict.incoming_value?.title as string) ??
    (conflict.incoming_value?.label as string) ??
    (conflict.incoming_value?.term as string) ??
    conflict.artifact_item_id;

  return (
    <button
      data-testid={`conflict-row-${conflict.id}`}
      onClick={onClick}
      className={`w-full text-left transition-colors ${
        selected
          ? "bg-buddy-gold/10 border-l-2 border-buddy-gold"
          : "hover:bg-buddy-elevated border-l-2 border-transparent"
      }`}
      style={{ padding: "6px 10px" }}
    >
      <div className="flex items-center gap-1.5">
        <span style={{ fontSize: 12 }}>{icon}</span>
        <span
          className="font-mono text-buddy-text-dim"
          style={{ fontSize: 9, flexShrink: 0 }}
        >
          {label}
        </span>
        <span
          className="text-buddy-text truncate"
          style={{ fontSize: 11, flex: 1, minWidth: 0 }}
          title={itemLabel}
        >
          {itemLabel}
        </span>
      </div>
      {conflict.source_context_name && (
        <div className="text-buddy-text-muted truncate" style={{ fontSize: 9, paddingLeft: 20 }}>
          from {conflict.source_context_name}
        </div>
      )}
      <div
        className="text-buddy-text-faint truncate"
        style={{ fontSize: 9, paddingLeft: 20 }}
        title={conflict.conflict_reason}
      >
        {conflict.conflict_reason}
      </div>
    </button>
  );
}
