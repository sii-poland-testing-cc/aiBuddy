"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Project {
  project_id: string;
  name: string;
  created_at?: string;
  files?: { filename: string }[];
}

export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects`);
      if (res.ok) setProjects(await res.json());
    } catch {
      // Backend offline — fail silently
    }
  }, []);

  const createProject = useCallback(
    async (name: string): Promise<Project | null> => {
      try {
        const res = await fetch(`${API_BASE}/api/projects`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });
        if (res.ok) {
          const project: Project = await res.json();
          setProjects((prev) => [...prev, project]);
          return project;
        }
      } catch {
        // ignore
      }
      return null;
    },
    []
  );

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  return { projects, fetchProjects, createProject };
}
