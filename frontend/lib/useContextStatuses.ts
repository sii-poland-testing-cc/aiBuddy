"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Batch-fetches context status for a list of project IDs in parallel.
 * Returns a Record<projectId, rag_ready>.
 */
export function useContextStatuses(projectIds: string[]): Record<string, boolean> {
  const [statuses, setStatuses] = useState<Record<string, boolean>>({});
  const key = projectIds.join(",");

  const fetchAll = useCallback(async () => {
    if (!projectIds.length) return;
    const pairs = await Promise.all(
      projectIds.map(async (id) => {
        try {
          const res = await fetch(
            `${API_BASE}/api/context/${encodeURIComponent(id)}/status`
          );
          if (!res.ok) return [id, false] as const;
          const data = await res.json();
          return [id, data.rag_ready === true] as const;
        } catch {
          return [id, false] as const;
        }
      })
    );
    setStatuses(Object.fromEntries(pairs));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  return statuses;
}
