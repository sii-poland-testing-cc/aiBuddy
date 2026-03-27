"use client";
import { useState, useEffect } from "react";
import type { WorkContext } from "../lib/useWorkContext";
import { usePromotion, type PromotionResult } from "../lib/usePromotion";

interface PromotionPreviewProps {
  projectId: string;
  context: WorkContext;
  parentName: string;
  onConfirm: (result: PromotionResult) => void;
  onCancel: () => void;
}

const ARTIFACT_LABELS: Record<string, string> = {
  requirement: "Requirements",
  graph_node: "Graph nodes",
  graph_edge: "Graph edges",
  glossary_term: "Glossary terms",
};

export default function PromotionPreview({
  projectId,
  context,
  parentName,
  onConfirm,
  onCancel,
}: PromotionPreviewProps) {
  const { preview, promote, loading, error } = usePromotion(projectId);
  const [previewResult, setPreviewResult] = useState<PromotionResult | null>(null);
  const [promoting, setPromoting] = useState(false);
  const [promoteError, setPromoteError] = useState<string | null>(null);

  useEffect(() => {
    preview(context.id).then(setPreviewResult).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context.id]);

  const handlePromote = async () => {
    setPromoting(true);
    setPromoteError(null);
    try {
      const result = await promote(context.id);
      onConfirm(result);
    } catch (e) {
      setPromoteError(e instanceof Error ? e.message : "Promotion failed");
    } finally {
      setPromoting(false);
    }
  };

  const cleanCount = previewResult ? previewResult.promoted_count : 0;
  const conflictCount = previewResult ? previewResult.conflict_count : 0;
  const totalFound = cleanCount + conflictCount;

  return (
    <div className="fixed inset-0 flex items-center justify-center" style={{ zIndex: 300 }}>
      <div className="absolute inset-0 bg-black/60" onClick={onCancel} />
      <div
        data-testid="promotion-preview-dialog"
        className="relative bg-buddy-surface2 border border-buddy-border rounded-[8px] shadow-2xl animate-fade-up"
        style={{ width: 460, maxHeight: "80vh", overflow: "auto", padding: 0 }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between border-b border-buddy-border"
          style={{ padding: "12px 16px" }}
        >
          <span className="font-semibold text-buddy-text" style={{ fontSize: 13 }}>
            ↑ Promote &quot;{context.name}&quot;
          </span>
          <span className="text-buddy-text-muted" style={{ fontSize: 11 }}>→ {parentName}</span>
          <button
            onClick={onCancel}
            className="text-buddy-text-dim hover:text-buddy-text ml-4"
            style={{ fontSize: 14 }}
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: "16px" }}>
          {loading && !previewResult ? (
            <p className="text-buddy-text-muted" style={{ fontSize: 12 }}>Loading preview…</p>
          ) : error && !previewResult ? (
            <p className="text-buddy-error" style={{ fontSize: 12 }}>⚠ {error}</p>
          ) : previewResult ? (
            <>
              {/* Clean items section */}
              {cleanCount > 0 && (
                <div style={{ marginBottom: 14 }}>
                  <div
                    className="font-medium text-buddy-success"
                    style={{ fontSize: 12, marginBottom: 6 }}
                  >
                    ✓ Ready to promote: {cleanCount} item{cleanCount !== 1 ? "s" : ""}
                  </div>
                  <div className="flex flex-col gap-1" style={{ paddingLeft: 12 }}>
                    {Object.entries(previewResult.artifact_type_summary).map(([type, s]) =>
                      s.promoted > 0 ? (
                        <div key={type} className="text-buddy-text-muted" style={{ fontSize: 11 }}>
                          • {ARTIFACT_LABELS[type] ?? type}: {s.promoted}
                          {s.version_deltas ? (
                            <span style={{ marginLeft: 6, fontSize: 10, color: "#60a5fa" }}>
                              ({s.version_deltas} version update{s.version_deltas !== 1 ? "s" : ""})
                            </span>
                          ) : null}
                        </div>
                      ) : null
                    )}
                  </div>
                </div>
              )}

              {/* Conflicts section */}
              {conflictCount > 0 && (
                <div
                  className="border border-buddy-error/20 rounded-[4px]"
                  style={{
                    marginBottom: 14,
                    padding: "8px 12px",
                    background: "rgba(200,90,58,0.06)",
                  }}
                >
                  <div
                    className="font-medium text-buddy-error"
                    style={{ fontSize: 12, marginBottom: 6 }}
                  >
                    ⚠ Conflicts detected: {conflictCount} item{conflictCount !== 1 ? "s" : ""}
                  </div>
                  <p className="text-buddy-text-dim" style={{ fontSize: 11, marginBottom: 6 }}>
                    These items will be queued for manual review:
                  </p>
                  <div className="flex flex-col gap-1" style={{ paddingLeft: 8 }}>
                    {Object.entries(previewResult.artifact_type_summary).map(([type, s]) =>
                      s.conflicts > 0 ? (
                        <div key={type} className="text-buddy-text-muted" style={{ fontSize: 11 }}>
                          • {ARTIFACT_LABELS[type] ?? type}: {s.conflicts} conflict
                          {s.conflicts !== 1 ? "s" : ""}
                        </div>
                      ) : null
                    )}
                  </div>
                </div>
              )}

              {/* Nothing to promote */}
              {totalFound === 0 && (
                <p
                  className="text-buddy-text-muted text-center"
                  style={{ fontSize: 12, padding: "8px 0" }}
                >
                  📭 No artifacts found in this context.
                </p>
              )}
            </>
          ) : null}

          {promoteError && (
            <p className="text-buddy-error" style={{ fontSize: 11, marginTop: 8 }}>
              {promoteError}
            </p>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-between border-t border-buddy-border"
          style={{ padding: "10px 16px" }}
        >
          <button
            onClick={onCancel}
            className="text-buddy-text-muted hover:text-buddy-text border border-buddy-border rounded-[4px] transition-colors"
            style={{ padding: "5px 14px", fontSize: 11 }}
          >
            Cancel
          </button>
          <div className="flex items-center gap-3">
            {conflictCount > 0 && (
              <span className="text-buddy-text-dim" style={{ fontSize: 10 }}>
                {conflictCount} conflict{conflictCount !== 1 ? "s" : ""} will be queued
              </span>
            )}
            <button
              data-testid="promotion-confirm-btn"
              disabled={promoting || loading}
              onClick={handlePromote}
              className="bg-buddy-success/15 border border-buddy-success/40 text-buddy-success hover:bg-buddy-success/25 disabled:opacity-40 disabled:cursor-not-allowed rounded-[4px] transition-colors font-medium"
              style={{ padding: "5px 16px", fontSize: 11 }}
            >
              {promoting
                ? "Promoting…"
                : conflictCount > 0
                ? `Promote Clean (${cleanCount})`
                : totalFound === 0
                ? "Promote Anyway"
                : `Promote All (${cleanCount})`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
