"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface VersionEntry {
  version_number: number;
  change_summary: string | null;
  created_by: string;
  created_at: string | null;
  created_in_context_id: string | null;
}

export interface ItemVersionInfo {
  current_version: number | null;
  pinned_version: number | null;
  has_newer: boolean;
  versions: VersionEntry[];
}

export interface DriftEntry {
  artifact_type: string;
  item_id: string;
  pinned_version: number;
  current_version: number;
}

/**
 * Fetch version history for a single artifact item.
 */
export function useItemVersionInfo(
  projectId: string,
  artifactType: string | null,
  itemId: string | null,
  contextId?: string | null,
) {
  const [info, setInfo] = useState<ItemVersionInfo | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!projectId || !artifactType || !itemId) {
      setInfo(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const params = contextId ? `?context_id=${encodeURIComponent(contextId)}` : "";
    fetch(`${API_BASE}/api/versions/${projectId}/${artifactType}/${encodeURIComponent(itemId)}${params}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data) {
          setInfo({
            current_version: data.current_version,
            pinned_version: data.pinned_version,
            has_newer: data.has_newer,
            versions: data.versions ?? [],
          });
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId, artifactType, itemId, contextId]);

  return { info, loading };
}

/**
 * Fetch version drift for all items in a context (batch).
 * Returns a map of "artifact_type:item_id" → DriftEntry.
 */
export function useVersionDrift(projectId: string, contextId: string | null | undefined) {
  const [drift, setDrift] = useState<Record<string, DriftEntry>>({});
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!projectId || !contextId) {
      setDrift({});
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/versions/${projectId}/drift?context_id=${encodeURIComponent(contextId)}`,
      );
      if (res.ok) {
        const data = await res.json();
        setDrift(data.drift ?? {});
      }
    } catch { /* fail silently */ }
    finally { setLoading(false); }
  }, [projectId, contextId]);

  useEffect(() => { refresh(); }, [refresh]);

  return { drift, loading, refresh };
}
