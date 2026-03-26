"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface WorkContext {
  id: string;
  name: string;
  level: "domain" | "epic" | "story" | string;
  status: "draft" | "active" | "ready" | "promoted" | "archived" | "conflict_pending" | string;
  parent_id: string | null;
  description?: string | null;
  promoted_at?: string | null;
  created_at?: string;
}

/** Flatten a nested tree response from the API into a flat list */
function flattenTree(nodes: (WorkContext & { children?: (WorkContext & { children?: unknown[] })[] })[]): WorkContext[] {
  const result: WorkContext[] = [];
  function visit(node: WorkContext & { children?: unknown[] }) {
    const { children, ...ctx } = node as WorkContext & { children?: unknown[] };
    result.push(ctx);
    if (Array.isArray(children)) {
      for (const child of children) visit(child as WorkContext & { children?: unknown[] });
    }
  }
  nodes.forEach(visit);
  return result;
}

export function useWorkContext(projectId: string) {
  const [contexts, setContexts] = useState<WorkContext[]>([]);
  const [currentContextId, setCurrentContextId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchContexts = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/work-contexts/${projectId}`);
      if (res.ok) {
        const data = await res.json();
        setContexts(flattenTree(data.contexts ?? []));
      }
    } catch { /* fail silently */ }
    finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { fetchContexts(); }, [fetchContexts]);

  const setContext = useCallback((id: string | null) => {
    setCurrentContextId(id);
  }, []);

  const createContext = useCallback(async (
    level: "epic" | "story",
    name: string,
    parentId: string,
    description?: string,
  ): Promise<WorkContext> => {
    const res = await fetch(`${API_BASE}/api/work-contexts/${projectId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level, name, parent_id: parentId, description: description ?? null }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as { detail?: string }).detail ?? "Failed to create context");
    }
    const created = await res.json() as WorkContext;
    await fetchContexts();
    return created;
  }, [projectId, fetchContexts]);

  const createDomain = useCallback(async (
    name: string,
    description?: string,
  ): Promise<WorkContext> => {
    const res = await fetch(`${API_BASE}/api/work-contexts/${projectId}/domain`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description: description ?? null }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as { detail?: string }).detail ?? "Failed to create domain");
    }
    const created = await res.json() as WorkContext;
    await fetchContexts();
    return created;
  }, [projectId, fetchContexts]);

  const updateContext = useCallback(async (
    id: string,
    patch: { name?: string; description?: string; status?: string },
  ): Promise<WorkContext> => {
    const res = await fetch(`${API_BASE}/api/work-contexts/${projectId}/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as { detail?: string }).detail ?? "Failed to update context");
    }
    const updated = await res.json() as WorkContext;
    await fetchContexts();
    return updated;
  }, [projectId, fetchContexts]);

  const archiveContext = useCallback(async (id: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/api/work-contexts/${projectId}/${id}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as { detail?: string }).detail ?? "Failed to archive context");
    }
    if (currentContextId === id) setCurrentContextId(null);
    await fetchContexts();
  }, [projectId, fetchContexts, currentContextId]);

  return {
    contexts,
    currentContextId,
    setContext,
    loading,
    createContext,
    createDomain,
    updateContext,
    archiveContext,
    refresh: fetchContexts,
  };
}
