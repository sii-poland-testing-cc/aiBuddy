"use client";
import { useState, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface PromotionResult {
  promoted_count: number;
  conflict_count: number;
  artifact_type_summary: Record<string, {
    items_found: number;
    promoted: number;
    conflicts: number;
    /** Count of items where pinned version differs from current (Phase 8.4). */
    version_deltas?: number;
  }>;
}

export function usePromotion(projectId: string) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const preview = useCallback(async (contextId: string): Promise<PromotionResult> => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/promotion/${projectId}/${contextId}/preview`);
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error((e as {detail?: string}).detail ?? "Preview failed");
      }
      return await res.json() as PromotionResult;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Preview failed";
      setError(msg); throw e;
    } finally { setLoading(false); }
  }, [projectId]);

  const promote = useCallback(async (contextId: string): Promise<PromotionResult> => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/promotion/${projectId}/${contextId}/promote`, { method: "POST" });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error((e as {detail?: string}).detail ?? "Promotion failed");
      }
      return await res.json() as PromotionResult;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Promotion failed";
      setError(msg); throw e;
    } finally { setLoading(false); }
  }, [projectId]);

  const clearError = useCallback(() => setError(null), []);

  return { preview, promote, loading, error, clearError };
}
