"use client";

import { useState, useCallback, useContext } from "react";
import { ProjectOperationsContext } from "./ProjectOperationsContext";
import { consumeSSE } from "./sseStream";
import { apiFetch } from "@/lib/apiFetch";

const OP_TYPE = "mapping" as const;

export interface MappingProgress {
  message: string;
  progress: number;
  stage: string;
}

export function useMapping(projectId: string, onComplete?: () => void) {
  const ops = useContext(ProjectOperationsContext);

  const [localIsRunning, setIsRunning] = useState(false);
  const [localProgress, setProgress] = useState<MappingProgress | null>(null);
  const [localError, setError] = useState<string | null>(null);
  const [lastRunAt, setLastRunAt] = useState<string | null>(null);

  // Context wins (survives navigation), local is fallback
  const ctxOp = ops?.getOp(projectId, OP_TYPE);
  const isRunning = ctxOp?.isRunning ?? localIsRunning;
  const progress: MappingProgress | null = ctxOp?.isRunning
    ? { message: ctxOp.message ?? "", progress: ctxOp.progress, stage: ctxOp.stage ?? "load" }
    : localProgress;
  const error = ctxOp?.error ?? localError;

  const runMapping = useCallback(async () => {
    if (!projectId || isRunning) return;
    setIsRunning(true);
    setError(null);
    setProgress({ message: "Łączenie z serwerem…", progress: 0, stage: "load" });
    ops?.updateOp(projectId, OP_TYPE, { isRunning: true, progress: 0, stage: "load", message: "Łączenie z serwerem…", error: null });

    try {
      const res = await apiFetch(`/api/mapping/${projectId}/run`, {
        method: "POST",
      });

      if (!res.ok) throw new Error(`Server error ${res.status}`);
      if (!res.body) throw new Error("No response body");

      await consumeSSE(res.body, (ev) => {
        if (ev.type === "progress") {
          setProgress(ev.data as MappingProgress);
          ops?.updateOp(projectId, OP_TYPE, { progress: ev.data.progress, stage: ev.data.stage, message: ev.data.message });
        } else if (ev.type === "result") {
          setLastRunAt(new Date().toISOString());
          onComplete?.();
        } else if (ev.type === "error") {
          const errMsg = ev.data?.message ?? "Mapowanie nie powiodło się.";
          setError(errMsg);
          ops?.updateOp(projectId, OP_TYPE, { error: errMsg });
        }
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      const errMsg = msg.includes("Server error") || msg.includes("No response")
        ? msg
        : "Nie udało się uruchomić mapowania. Sprawdź połączenie z serwerem.";
      setError(errMsg);
      ops?.updateOp(projectId, OP_TYPE, { error: errMsg });
    } finally {
      setIsRunning(false);
      setProgress(null);
      ops?.updateOp(projectId, OP_TYPE, { isRunning: false });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, isRunning, onComplete, ops]);

  return { isRunning, progress, error, lastRunAt, runMapping };
}
