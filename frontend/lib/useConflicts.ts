"use client";
import { useState, useCallback, useEffect, useMemo } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Conflict {
  id: string;
  project_id: string;
  artifact_type: "graph_node" | "graph_edge" | "glossary_term" | "requirement";
  artifact_item_id: string;
  source_context_id: string;
  target_context_id: string;
  incoming_value: Record<string, unknown>;
  existing_value: Record<string, unknown>;
  conflict_reason: string;
  status: "pending" | "resolved_accept_new" | "resolved_keep_old" | "resolved_edited" | "deferred";
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_value: Record<string, unknown> | null;
  created_at: string;
  source_context_name: string | null;
  source_context_level: string | null;
  target_context_name: string | null;
  target_context_level: string | null;
}

export type ResolutionType = "accept_new" | "keep_old" | "edited" | "defer";

export function useConflicts(projectId: string) {
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (artifactType?: string, contextId?: string) => {
    if (!projectId) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (artifactType) params.set("artifact_type", artifactType);
      if (contextId) params.set("context_id", contextId);
      const url = `${API_BASE}/api/conflicts/${projectId}${params.toString() ? `?${params}` : ""}`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setConflicts(data.conflicts ?? []);
      }
    } catch { /* fail silently */ }
    finally { setLoading(false); }
  }, [projectId]);

  const resolve = useCallback(async (
    conflictId: string,
    resolution: ResolutionType,
    resolvedValue?: Record<string, unknown> | null,
    note?: string | null,
  ) => {
    const res = await fetch(`${API_BASE}/api/conflicts/${projectId}/${conflictId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resolution, resolved_value: resolvedValue ?? null, note: note ?? null }),
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      throw new Error((e as {detail?: string}).detail ?? "Resolution failed");
    }
    const data = await res.json();
    await refresh(); // re-fetch pending list
    return data as { conflict: Conflict; retry_result: { promoted_count: number; conflict_count: number } | null };
  }, [projectId, refresh]);

  useEffect(() => { refresh(); }, [refresh]);

  const pendingCount = useMemo(() => conflicts.filter(c => c.status === "pending").length, [conflicts]);

  return { conflicts, loading, error, pendingCount, refresh, resolve };
}
