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

export interface ExtractionProgress {
  message: string;
  progress: number;
  stage: string;
}

export function useRequirements(projectId: string) {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [stats, setStats] = useState<RequirementsStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionProgress, setExtractionProgress] = useState<ExtractionProgress | null>(null);

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

  const extractRequirements = useCallback(async (message = "") => {
    if (!projectId || isExtracting) return;
    setIsExtracting(true);
    setError(null);
    setExtractionProgress({ message: "Łączenie z serwerem…", progress: 0, stage: "extract" });

    try {
      const res = await fetch(`${API_BASE}/api/requirements/${projectId}/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });

      if (!res.ok) throw new Error(`Server error ${res.status}`);
      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") break;
          try {
            const ev = JSON.parse(payload);
            if (ev.type === "progress") {
              setExtractionProgress(ev.data as ExtractionProgress);
            } else if (ev.type === "result") {
              // Stream complete — reload requirements from DB
              await fetchAll();
            } else if (ev.type === "error") {
              setError(ev.data?.message ?? "Ekstrakcja nie powiodła się.");
            }
          } catch {
            // malformed line — skip
          }
        }
      }
    } catch {
      setError("Nie udało się wyodrębnić wymagań. Sprawdź czy kontekst projektu jest zbudowany.");
    } finally {
      setIsExtracting(false);
      setExtractionProgress(null);
    }
  }, [projectId, isExtracting, fetchAll]);

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
    isExtracting,
    extractionProgress,
    patchRequirement,
    extractRequirements,
    refresh: fetchAll,
    retry: fetchAll,
  };
}
