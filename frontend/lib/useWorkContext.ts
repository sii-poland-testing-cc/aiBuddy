"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface WorkContext {
  id: string;
  name: string;
  level: "domain" | "epic" | "story" | string;
  status: string;
  parent_id: string | null;
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
        setContexts(data.contexts ?? []);
      }
    } catch {
      /* fail silently */
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchContexts();
  }, [fetchContexts]);

  const setContext = useCallback((id: string | null) => {
    setCurrentContextId(id);
  }, []);

  return { contexts, currentContextId, setContext, loading };
}
