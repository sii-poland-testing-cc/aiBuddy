"use client";

import { useState, useRef, useEffect, useContext } from "react";
import { useRouter } from "next/navigation";
import { useProjects } from "../lib/useProjects";
import { useContextStatuses } from "../lib/useContextStatuses";
import { ProjectOperationsContext } from "../lib/ProjectOperationsContext";
import ProjectList from "../components/ProjectList";

export default function Home() {
  const router = useRouter();
  const { projects, createProject } = useProjects();
  const statuses = useContextStatuses(projects.map((p) => p.project_id));
  const opsCtx = useContext(ProjectOperationsContext);
  const runningProjects = opsCtx?.runningProjects ?? new Set<string>();

  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (creating) inputRef.current?.focus();
  }, [creating]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name || submitting) return;
    setSubmitting(true);
    const project = await createProject(name);
    setSubmitting(false);
    if (project) {
      router.push(`/project/${encodeURIComponent(project.project_id)}`);
    }
  };

  const formatDate = (iso?: string) => {
    if (!iso) return "";
    return new Date(iso).toLocaleDateString("pl-PL", {
      day: "numeric", month: "short", year: "numeric",
    });
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-buddy-base p-8">
      <div className="w-full max-w-[420px] px-2">

        {/* Logo + title */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-buddy-gold to-buddy-gold-light text-xl font-bold text-buddy-surface mb-4">
            Q
          </div>
          <h1 className="text-xl font-semibold text-buddy-text">AI Buddy</h1>
          <p className="text-sm text-buddy-text-muted mt-1">QA Agent Platform</p>
        </div>

        {/* Project list */}
        <ProjectList
          projects={projects}
          runningProjects={runningProjects}
          statuses={statuses}
          formatDate={formatDate}
        />

        {/* Create form / dashed button */}
        {creating ? (
          <form onSubmit={handleCreate} className="flex gap-2">
            <input
              ref={inputRef}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && setCreating(false)}
              placeholder="Nazwa projektu…"
              className="flex-1 bg-buddy-elevated border border-buddy-border-dark rounded-xl px-4 py-3 text-sm text-buddy-text placeholder:text-buddy-text-faint focus:outline-none focus:border-buddy-gold"
            />
            <button
              type="submit"
              disabled={!newName.trim() || submitting}
              className="px-4 py-3 bg-buddy-gold rounded-xl text-sm font-medium text-buddy-surface hover:bg-buddy-gold-light disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              {submitting ? "…" : "Utwórz"}
            </button>
          </form>
        ) : (
          <button
            onClick={() => setCreating(true)}
            className="w-full py-3 text-sm text-buddy-text-muted hover:text-buddy-gold-light border border-dashed border-buddy-border-dark rounded-xl hover:border-buddy-gold transition-all"
          >
            + Nowy projekt
          </button>
        )}
      </div>
    </main>
  );
}
