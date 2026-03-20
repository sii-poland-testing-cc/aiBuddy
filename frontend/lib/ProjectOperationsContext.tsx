"use client";

import { createContext, useContext, useRef, useState, useMemo, useCallback } from "react";

// ── Types ──────────────────────────────────────────────────────────────────────

export type OpType = "contextBuild" | "requirements" | "mapping";

export interface OpState {
  isRunning: boolean;
  progress: number;    // 0–1
  stage: string | null;
  message: string | null;
  error: string | null;
}

const DEFAULT_OP: OpState = {
  isRunning: false,
  progress: 0,
  stage: null,
  message: null,
  error: null,
};

// ── Context ────────────────────────────────────────────────────────────────────

interface ProjectOperationsContextValue {
  getOp: (projectId: string, opType: OpType) => OpState;
  updateOp: (projectId: string, opType: OpType, patch: Partial<OpState>) => void;
  clearOp: (projectId: string, opType: OpType) => void;
  runningProjects: Set<string>;
}

export const ProjectOperationsContext =
  createContext<ProjectOperationsContextValue | null>(null);

// ── Provider ───────────────────────────────────────────────────────────────────

export function ProjectOperationsProvider({ children }: { children: React.ReactNode }) {
  // Ref holds the data — no re-render on every write
  const storeRef = useRef<Map<string, Map<OpType, OpState>>>(new Map());
  // Version counter triggers re-renders when ops change
  const [version, setVersion] = useState(0);

  const getOp = useCallback((projectId: string, opType: OpType): OpState => {
    return storeRef.current.get(projectId)?.get(opType) ?? DEFAULT_OP;
  }, []);

  const updateOp = useCallback((projectId: string, opType: OpType, patch: Partial<OpState>) => {
    const store = storeRef.current;
    if (!store.has(projectId)) store.set(projectId, new Map());
    const projectOps = store.get(projectId)!;
    const current = projectOps.get(opType) ?? { ...DEFAULT_OP };
    projectOps.set(opType, { ...current, ...patch });
    setVersion((v) => v + 1);
  }, []);

  const clearOp = useCallback((projectId: string, opType: OpType) => {
    storeRef.current.get(projectId)?.delete(opType);
    setVersion((v) => v + 1);
  }, []);

  const runningProjects = useMemo(() => {
    // eslint-disable-next-line @typescript-eslint/no-unused-expressions
    version; // subscribe to version changes
    const running = new Set<string>();
    storeRef.current.forEach((ops, projectId) => {
      ops.forEach((op) => {
        if (op.isRunning) running.add(projectId);
      });
    });
    return running;
  }, [version]);

  return (
    <ProjectOperationsContext.Provider value={{ getOp, updateOp, clearOp, runningProjects }}>
      {children}
    </ProjectOperationsContext.Provider>
  );
}

// ── Convenience hook ───────────────────────────────────────────────────────────

export function useProjectOps() {
  return useContext(ProjectOperationsContext);
}
