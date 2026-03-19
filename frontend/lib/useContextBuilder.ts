"use client";

import { useState, useCallback, useEffect } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  related_terms: string[];
  source: string;
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
  const [isBuilding, setIsBuilding] = useState(false);
  const [stage, setStage]     = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [log, setLog]         = useState<string[]>([]);
  const [result, setResult]   = useState<ContextResult | null>(null);
  const [status, setStatus]   = useState<ContextStatus | null>(null);
  const [error, setError]     = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_BASE}/api/context/${encodeURIComponent(projectId)}/status`
      );
      if (res.ok) setStatus(await res.json());
    } catch {
      /* backend offline — fail silently */
    }
  }, [projectId]);

  const fetchArtefacts = useCallback(async () => {
    try {
      const [mmRes, glRes] = await Promise.all([
        fetch(`${API_BASE}/api/context/${encodeURIComponent(projectId)}/mindmap`),
        fetch(`${API_BASE}/api/context/${encodeURIComponent(projectId)}/glossary`),
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
    setIsBuilding(true);
    setLog([]);
    setStage("parse");
    setProgress(0);
    setError(null);

    try {
      let res: Response;
      if (files.length === 0) {
        // No new files supplied — rebuild from documents already on disk
        res = await fetch(
          `${API_BASE}/api/context/${encodeURIComponent(projectId)}/rebuild-existing?mode=${mode}`,
          { method: "POST" }
        );
      } else {
        const formData = new FormData();
        for (const f of files) formData.append("files", f);
        res = await fetch(
          `${API_BASE}/api/context/${encodeURIComponent(projectId)}/build?mode=${mode}`,
          { method: "POST", body: formData }
        );
      }
      if (!res.ok) throw new Error(`Server error ${res.status}: ${await res.text()}`);
      if (!res.body) throw new Error("No response body");

      const reader  = res.body.getReader();
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
              setStage(ev.data.stage);
              setProgress(ev.data.progress);
              setLog((prev) => [...prev, ev.data.message]);
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
            }
          } catch { /* malformed line */ }
        }
      }
      // Refresh status to pick up context_files and document_count
      await fetchStatus();
    } catch (err: any) {
      if (err.name !== "AbortError") {
        setError(err.message || "Nie udało się zbudować kontekstu. Sprawdź czy pliki są w formacie .docx lub .pdf.");
      }
    } finally {
      setIsBuilding(false);
    }
  // fetchStatus is stable (useCallback with [projectId])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  // On page load, if artefacts already exist, hydrate result from the GET endpoints
  useEffect(() => {
    if (status?.artefacts_ready && !result) fetchArtefacts();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.artefacts_ready]);

  return { isBuilding, stage, progress, log, result, status, error, buildContext, fetchStatus, retry: fetchStatus, clearError: () => setError(null) };
}
