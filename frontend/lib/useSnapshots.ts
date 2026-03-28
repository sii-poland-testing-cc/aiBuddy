import { useState, useEffect, useCallback } from "react";
import type { AuditSnapshot } from "./types";
import { apiFetch } from "@/lib/apiFetch";

export function useSnapshots(projectId: string, latestSnapshotId?: string | null): AuditSnapshot[] {
  const [snapshots, setSnapshots] = useState<AuditSnapshot[]>([]);

  const fetchSnapshots = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/snapshots/${projectId}`);
      if (res.ok) {
        const data = await res.json();
        setSnapshots(
          data.map((s: any) => ({
            id: s.id,
            created_at: s.created_at,
            summary: typeof s.summary === "string" ? JSON.parse(s.summary) : s.summary,
            diff: typeof s.diff === "string" ? JSON.parse(s.diff) : s.diff,
            requirements_uncovered: Array.isArray(s.requirements_uncovered) ? s.requirements_uncovered : [],
            recommendations: Array.isArray(s.recommendations) ? s.recommendations : [],
            files_used: Array.isArray(s.files_used) ? s.files_used : [],
          }))
        );
      }
    } catch {
      /* backend offline */
    }
  }, [projectId]);

  useEffect(() => { fetchSnapshots(); }, [fetchSnapshots]);
  // Re-fetch when a new audit completes
  useEffect(() => { if (latestSnapshotId) fetchSnapshots(); }, [latestSnapshotId, fetchSnapshots]);

  return snapshots;
}
