"use client";

import { useState, useCallback, useEffect, useContext } from "react";
import { ProjectOperationsContext } from "./ProjectOperationsContext";
import { consumeSSE } from "./sseStream";
import { apiFetch } from "@/lib/apiFetch";

const OP_TYPE = "contextBuild" as const;

// ── Types ──────────────────────────────────────────────────────────────────────

export interface ContextStatus {
  project_id: string;
  rag_ready: boolean;
  artefacts_ready: boolean;
  stats: { entity_count: number; relation_count: number; term_count: number } | null;
  context_built_at?: string | null;
  context_files?: string[] | null;
  document_count?: number;
}

export interface MindMapNode {
  id: string;
  label: string;
  type: string;
  description: string;
}

export interface MindMapEdge {
  source: string;
  target: string;
  label: string;
}

export interface GlossaryTerm {
  term: string;
  definition: string;
  related_terms?: string[];
  source?: string;
}

export interface ContextResult {
  project_id: string;
  rag_ready: boolean;
  mind_map: { nodes: MindMapNode[]; edges: MindMapEdge[] };
  glossary: GlossaryTerm[];
  stats: { entity_count: number; relation_count: number; term_count: number };
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useContextBuilder(projectId: string) {
  const ops = useContext(ProjectOperationsContext);

  const [localIsBuilding, setIsBuilding] = useState(false);
  const [localStage, setStage]     = useState<string | null>(null);
  const [localProgress, setProgress] = useState(0);
  const [log, setLog]         = useState<string[]>([]);
  const [result, setResult]       = useState<ContextResult | null>(null);
  const [status, setStatus]       = useState<ContextStatus | null>(null);
  const [localError, setError]    = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Context wins (survives navigation), local is fallback
  const ctxOp = ops?.getOp(projectId, OP_TYPE);
  const isBuilding = ctxOp?.isRunning ?? localIsBuilding;
  const stage      = ctxOp?.stage     ?? localStage;
  const progress   = ctxOp?.progress  ?? localProgress;
  const error      = ctxOp?.error     ?? localError;

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiFetch(
        `/api/context/${encodeURIComponent(projectId)}/status`
      );
      if (res.ok) {
        setStatus(await res.json());
        setStatusError(null);
      }
    } catch {
      setStatusError("Nie można połączyć z serwerem. Sprawdź czy backend jest uruchomiony.");
    }
  }, [projectId]);

  const fetchArtefacts = useCallback(async () => {
    try {
      const [mmRes, glRes] = await Promise.all([
        apiFetch(`/api/context/${encodeURIComponent(projectId)}/mindmap`),
        apiFetch(`/api/context/${encodeURIComponent(projectId)}/glossary`),
      ]);
      if (!mmRes.ok || !glRes.ok) return;
      const [mind_map, glossary] = await Promise.all([mmRes.json(), glRes.json()]);
      setResult((prev) =>
        prev
          ? prev
          : {
              project_id: projectId,
              rag_ready: true,
              mind_map,
              glossary,
              stats: { entity_count: mind_map.nodes?.length ?? 0, relation_count: mind_map.edges?.length ?? 0, term_count: glossary.length ?? 0 },
            }
      );
    } catch {
      /* fail silently */
    }
  }, [projectId]);

  const buildContext = useCallback(async (files: File[], mode: "append" | "rebuild" = "append") => {
    if (isBuilding) return;
    setIsBuilding(true);
    setLog([]);
    setStage("parse");
    setProgress(0);
    setError(null);
    ops?.updateOp(projectId, OP_TYPE, { isRunning: true, progress: 0, stage: "parse", message: null, error: null });

    try {
      let res: Response;
      if (files.length === 0) {
        // No new files supplied — rebuild from documents already on disk
        res = await apiFetch(
          `/api/context/${encodeURIComponent(projectId)}/rebuild-existing?mode=${mode}`,
          { method: "POST" }
        );
      } else {
        const formData = new FormData();
        for (const f of files) formData.append("files", f);
        res = await apiFetch(
          `/api/context/${encodeURIComponent(projectId)}/build?mode=${mode}`,
          { method: "POST", body: formData }
        );
      }
      if (!res.ok) throw new Error(`Server error ${res.status}: ${await res.text()}`);
      if (!res.body) throw new Error("No response body");

      await consumeSSE(res.body, (ev) => {
        if (ev.type === "progress") {
          setStage(ev.data.stage);
          setProgress(ev.data.progress);
          setLog((prev) => [...prev, ev.data.message]);
          ops?.updateOp(projectId, OP_TYPE, { progress: ev.data.progress, stage: ev.data.stage, message: ev.data.message });
        } else if (ev.type === "result") {
          setResult(ev.data as ContextResult);
          setStatus({
            project_id: ev.data.project_id,
            rag_ready: ev.data.rag_ready,
            artefacts_ready: true,
            stats: ev.data.stats,
            context_built_at: new Date().toISOString(),
          });
        } else if (ev.type === "error") {
          setError(ev.data.message);
          ops?.updateOp(projectId, OP_TYPE, { error: ev.data.message });
        }
      });
      // Refresh status to pick up context_files and document_count
      await fetchStatus();
    } catch (err: any) {
      if (err.name !== "AbortError") {
        const msg = err.message || "Nie udało się zbudować kontekstu. Sprawdź czy pliki są w formacie .docx lub .pdf.";
        setError(msg);
        ops?.updateOp(projectId, OP_TYPE, { error: msg });
      }
    } finally {
      setIsBuilding(false);
      setProgress(0);
      setStage(null);
      ops?.updateOp(projectId, OP_TYPE, { isRunning: false, progress: 0, stage: null });
    }
  // fetchStatus is stable (useCallback with [projectId]); ops is stable (context)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, ops, isBuilding]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  // On page load, if artefacts already exist, hydrate result from the GET endpoints
  useEffect(() => {
    if (status?.artefacts_ready && !result) fetchArtefacts();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.artefacts_ready]);

  return { isBuilding, stage, progress, log, result, status, error, statusError, buildContext, fetchStatus, retry: fetchStatus, clearError: () => { setError(null); ops?.updateOp(projectId, OP_TYPE, { error: null }); }, clearStatusError: () => setStatusError(null) };
}
