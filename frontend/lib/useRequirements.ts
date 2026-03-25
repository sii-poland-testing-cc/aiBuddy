"use client";

import { useState, useEffect, useRef, useCallback, useContext } from "react";
import { ProjectOperationsContext } from "./ProjectOperationsContext";
import { consumeSSE } from "./sseStream";

const OP_TYPE = "requirements" as const;

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Mirrors backend `requirements_models.py` Requirement.level enum values. */
export type RequirementLevel =
  | "domain_concept"
  | "feature"
  | "functional_req"
  | "acceptance_criterion"
  | (string & Record<never, never>);  // allow future backend values without breaking TS

/** Mirrors backend Requirement.source_type enum values. */
export type RequirementSourceType =
  | "formal"
  | "implicit"
  | "reconstructed"
  | (string & Record<never, never>);  // allow future backend values without breaking TS

export interface Requirement {
  id: string;
  parent_id: string | null;
  level: RequirementLevel;
  external_id: string | null;
  title: string;
  description: string;
  source_type: RequirementSourceType;
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
  const ops = useContext(ProjectOperationsContext);

  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [stats, setStats] = useState<RequirementsStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localIsExtracting, setIsExtracting] = useState(false);
  const [localExtractionProgress, setExtractionProgress] = useState<ExtractionProgress | null>(null);

  // Context wins (survives navigation), local is fallback
  const ctxOp = ops?.getOp(projectId, OP_TYPE);
  const isExtracting = ctxOp?.isRunning ?? localIsExtracting;
  const extractionProgress: ExtractionProgress | null = ctxOp?.isRunning
    ? { message: ctxOp.message ?? "", progress: ctxOp.progress, stage: ctxOp.stage ?? "extract" }
    : localExtractionProgress;

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
    ops?.updateOp(projectId, OP_TYPE, { isRunning: true, progress: 0, stage: "extract", message: "Łączenie z serwerem…", error: null });

    try {
      const res = await fetch(`${API_BASE}/api/requirements/${projectId}/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });

      if (!res.ok) throw new Error(`Server error ${res.status}`);
      if (!res.body) throw new Error("No response body");

      await consumeSSE(res.body, async (ev) => {
        if (ev.type === "progress") {
          setExtractionProgress(ev.data as ExtractionProgress);
          ops?.updateOp(projectId, OP_TYPE, { progress: ev.data.progress, stage: ev.data.stage, message: ev.data.message });
        } else if (ev.type === "result") {
          // Stream complete — reload requirements from DB
          await fetchAll();
        } else if (ev.type === "error") {
          const errMsg = ev.data?.message ?? "Ekstrakcja nie powiodła się.";
          setError(errMsg);
          ops?.updateOp(projectId, OP_TYPE, { error: errMsg });
        }
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      const errMsg = msg.includes("Server error") || msg.includes("No response")
        ? msg
        : "Nie udało się wyodrębnić wymagań. Sprawdź połączenie z serwerem i czy kontekst projektu jest zbudowany.";
      setError(errMsg);
      ops?.updateOp(projectId, OP_TYPE, { error: errMsg });
    } finally {
      setIsExtracting(false);
      setExtractionProgress(null);
      ops?.updateOp(projectId, OP_TYPE, { isRunning: false });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, isExtracting, fetchAll, ops]);

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

  // When isExtracting transitions true→false (e.g. extraction finished while
  // user had navigated away and returned), reload requirements from DB.
  const prevIsExtractingRef = useRef<boolean>(isExtracting);
  useEffect(() => {
    const wasExtracting = prevIsExtractingRef.current;
    prevIsExtractingRef.current = isExtracting;
    if (wasExtracting && !isExtracting) {
      fetchAll();
    }
  }, [isExtracting, fetchAll]);

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
