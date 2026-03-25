"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Project } from "../lib/useProjects";

interface Props {
  projects: Project[];
  currentProjectId: string;
  statuses: Record<string, boolean>;
  onCreateProject: (name: string) => Promise<Project | null>;
}

export function ProjectSwitcherDropdown({
  projects,
  currentProjectId,
  statuses,
  onCreateProject,
}: Props) {
  const router = useRouter();

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const createInputRef = useRef<HTMLInputElement>(null);

  const currentProject = projects.find((p) => p.project_id === currentProjectId);
  const displayName = currentProject?.name ?? currentProjectId;

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
        setCreating(false);
        setNewName("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    if (creating) createInputRef.current?.focus();
  }, [creating]);

  const handleSelect = (id: string) => {
    setDropdownOpen(false);
    setCreating(false);
    setNewName("");
    if (id !== currentProjectId) router.push(`/project/${encodeURIComponent(id)}`);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name || submitting) return;
    setSubmitting(true);
    const project = await onCreateProject(name);
    setSubmitting(false);
    if (project) {
      setDropdownOpen(false);
      setCreating(false);
      setNewName("");
      router.push(`/project/${encodeURIComponent(project.project_id)}`);
    }
  };

  return (
    <div className="flex items-center flex-1 min-w-0" ref={dropdownRef}>
      <div className="relative">
        <button
          data-testid="project-switcher-btn"
          onClick={() => { setDropdownOpen((o) => !o); setCreating(false); setNewName(""); }}
          className="flex items-center border border-transparent rounded-[8px]
                     hover:bg-buddy-elevated transition-colors"
          style={{ gap: 7, padding: "5px 10px", maxWidth: 200 }}
        >
          {/* Logo mark */}
          <div
            className="bg-gradient-to-br from-buddy-gold to-buddy-gold-light
                       flex items-center justify-center font-bold text-buddy-surface shrink-0"
            style={{ width: 22, height: 22, borderRadius: 5, fontSize: 11 }}
          >
            Q
          </div>

          {/* Project name */}
          <span
            className="font-medium text-buddy-text truncate"
            style={{ fontSize: 13, maxWidth: 140 }}
          >
            {displayName}
          </span>

          {/* Chevron */}
          <span className="text-buddy-text-dim shrink-0" style={{ fontSize: 10 }}>▾</span>
        </button>

        {dropdownOpen && (
          <div
            data-testid="project-dropdown"
            className="absolute left-0 bg-buddy-surface border border-buddy-border-light
                       shadow-lg overflow-hidden z-[200]"
            style={{ top: "calc(100% + 6px)", width: 264, borderRadius: 8 }}
          >
            {/* Project list */}
            <div className="overflow-y-auto p-1" style={{ maxHeight: 280 }}>
              {projects.map((p) => {
                const isActive = p.project_id === currentProjectId;
                return (
                  <div
                    key={p.project_id}
                    className={`flex items-center group/row rounded-[5px] transition-colors
                                ${isActive ? "bg-buddy-elevated" : "hover:bg-buddy-elevated"}`}
                  >
                    <button
                      onClick={() => handleSelect(p.project_id)}
                      className="flex-1 text-left flex items-center gap-2 min-w-0"
                      style={{ padding: "7px 10px" }}
                    >
                      <span
                        className={`rounded-full shrink-0 ${
                          statuses[p.project_id] ? "bg-buddy-success" : "bg-buddy-text-dim"
                        }`}
                        style={{ width: 7, height: 7 }}
                      />
                      <span className="text-buddy-text-muted truncate flex-1" style={{ fontSize: 12 }}>
                        {p.name}
                      </span>
                      {isActive && (
                        <span className="text-buddy-gold shrink-0" style={{ fontSize: 11 }}>✓</span>
                      )}
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setDropdownOpen(false);
                        router.push(`/project/${encodeURIComponent(p.project_id)}/settings`);
                      }}
                      title="Ustawienia projektu"
                      className="shrink-0 px-2 text-buddy-text-dim opacity-0 group-hover/row:opacity-100
                                 hover:text-buddy-gold-light transition-all"
                      style={{ fontSize: 12, paddingTop: 7, paddingBottom: 7 }}
                    >
                      ⚙
                    </button>
                  </div>
                );
              })}
            </div>

            {/* Footer */}
            <div className="border-t border-buddy-border p-2 flex flex-col gap-1">
              {creating ? (
                <form onSubmit={handleCreate} className="flex gap-1.5 px-1 py-1">
                  <input
                    ref={createInputRef}
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Escape") { setCreating(false); setNewName(""); } }}
                    placeholder="Nazwa projektu…"
                    className="flex-1 bg-buddy-elevated border border-buddy-border-dark rounded-[5px]
                               text-buddy-text placeholder:text-buddy-text-faint
                               focus:outline-none focus:border-buddy-gold"
                    style={{ padding: "5px 10px", fontSize: 12 }}
                  />
                  <button
                    type="submit"
                    disabled={!newName.trim() || submitting}
                    className="bg-buddy-gold rounded-[5px] font-medium text-buddy-surface
                               disabled:opacity-40 disabled:cursor-not-allowed
                               hover:bg-buddy-gold-light transition-colors"
                    style={{ padding: "5px 10px", fontSize: 12 }}
                  >
                    {submitting ? "…" : "Utwórz"}
                  </button>
                </form>
              ) : (
                <button
                  onClick={() => setCreating(true)}
                  className="w-full text-left flex items-center rounded-[5px]
                             text-buddy-text-muted hover:bg-buddy-elevated hover:text-buddy-gold
                             transition-colors"
                  style={{ gap: 6, padding: "6px 8px", fontSize: 12 }}
                >
                  <svg width="13" height="13" viewBox="0 0 14 14" fill="none"
                       stroke="currentColor" strokeWidth="1.5">
                    <line x1="7" y1="3" x2="7" y2="11" />
                    <line x1="3" y1="7" x2="11" y2="7" />
                  </svg>
                  Nowy projekt
                </button>
              )}

              <button
                onClick={() => { setDropdownOpen(false); router.push("/"); }}
                className="w-full text-left rounded-[5px] text-buddy-text-dim
                           hover:text-buddy-text-muted transition-colors"
                style={{ padding: "5px 8px", fontSize: 12 }}
              >
                Wszystkie projekty →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
