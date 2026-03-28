"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/apiFetch";

export interface HeatmapRow {
  module: string;
  total_requirements: number;
  covered: number;
  avg_score: number;
  color: "green" | "yellow" | "orange" | "red";
}

function scoreToColor(avg: number): "green" | "yellow" | "orange" | "red" {
  if (avg >= 80) return "green";
  if (avg >= 60) return "yellow";
  if (avg >= 30) return "orange";
  return "red";
}

export function useHeatmap(projectId: string) {
  const [heatmap, setHeatmap] = useState<HeatmapRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchHeatmap = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(
        `/api/mapping/${projectId}/heatmap`
      );
      if (!res.ok) {
        setHeatmap([]);
        return;
      }
      const data = await res.json();
      const modules: HeatmapRow[] = (data.modules ?? []).map(
        (m: {
          module: string;
          total_requirements: number;
          covered_count?: number;
          avg_score: number;
        }) => ({
          module: m.module,
          total_requirements: m.total_requirements,
          covered: m.covered_count ?? 0,
          avg_score: m.avg_score,
          color: scoreToColor(m.avg_score),
        })
      );
      setHeatmap(modules);
    } catch {
      setHeatmap([]);
      setError("Nie udało się pobrać heatmapy pokrycia.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchHeatmap();
  }, [fetchHeatmap]);

  return { heatmap, loading, error, retry: fetchHeatmap };
}
