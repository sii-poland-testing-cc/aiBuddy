"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Requirement {
  id: string;
  parent_id: string | null;
  level: string;
  external_id: string | null;
  title: string;
  description: string;
  source_type: string;
  confidence: number;
  human_reviewed: boolean;
  needs_review: boolean;
  review_reason: string | null;
  taxonomy: { module?: string; risk_level?: string; business_domain?: string } | null;
}

export interface RequirementsStats {
  total: number;
  by_level: Record<string, number>;
  by_source_type: Record<string, number>;
  needs_review_count: number;
  human_reviewed_count: number;
}

export function useRequirements(projectId: string) {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [stats, setStats] = useState<RequirementsStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [flatRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/requirements/${projectId}/flat`),
        fetch(`${API_BASE}/api/requirements/${projectId}/stats`),
      ]);

      if (flatRes.ok) {
        const data = await flatRes.json();
        setRequirements(data.requirements ?? []);
      } else {
        setRequirements([]);
      }

      if (statsRes.ok) {
        const data = await statsRes.json();
        if (data.has_requirements === false) {
          setStats(null);
        } else {
          setStats({
            total: data.total ?? 0,
            by_level: data.by_level ?? {},
            by_source_type: data.by_source_type ?? {},
            needs_review_count: data.needs_review_count ?? 0,
            human_reviewed_count: data.human_reviewed_count ?? 0,
          });
        }
      } else {
        setStats(null);
      }
    } catch {
      setError("Nie udało się pobrać wymagań. Sprawdź połączenie z serwerem.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const patchRequirement = useCallback(
    async (
      reqId: string,
      patch: {
        human_reviewed?: boolean;
        needs_review?: boolean;
        title?: string;
        description?: string;
      }
    ) => {
      // Optimistic update
      setRequirements((prev) =>
        prev.map((r) => (r.id === reqId ? { ...r, ...patch } : r))
      );
      if (patch.human_reviewed === true) {
        setStats((prev) =>
          prev
            ? {
                ...prev,
                human_reviewed_count: prev.human_reviewed_count + 1,
                needs_review_count: patch.needs_review === false
                  ? Math.max(0, prev.needs_review_count - 1)
                  : prev.needs_review_count,
              }
            : prev
        );
      }

      try {
        const res = await fetch(
          `${API_BASE}/api/requirements/${projectId}/${reqId}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
          }
        );
        if (!res.ok) {
          // Revert on failure
          await fetchAll();
        }
      } catch {
        await fetchAll();
      }
    },
    [projectId, fetchAll]
  );

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return {
    requirements,
    stats,
    loading,
    error,
    patchRequirement,
    refresh: fetchAll,
    retry: fetchAll,
  };
}
