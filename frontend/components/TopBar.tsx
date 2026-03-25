"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useProjects } from "../lib/useProjects";
import { useContextStatuses } from "../lib/useContextStatuses";

interface TopBarProps {
  projectId: string;
  onTogglePanel: () => void;
  panelOpen: boolean;
  ragReady: boolean;
}

export default function TopBar({ projectId, onTogglePanel, panelOpen, ragReady }: TopBarProps) {
  const router = useRouter();
  const { projects, createProject } = useProjects();
  const statuses = useContextStatuses(projects.map((p) => p.project_id));

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const createInputRef = useRef<HTMLInputElement>(null);

  const currentProject = projects.find((p) => p.project_id === projectId);
  const displayName = currentProject?.name ?? projectId;

  // Close dropdown on outside click
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

  const handleSelectProject = (id: string) => {
    setDropdownOpen(false);
    setCreating(false);
    setNewName("");
    if (id !== projectId) router.push(`/project/${encodeURIComponent(id)}`);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name || submitting) return;
    setSubmitting(true);
    const project = await createProject(name);
    setSubmitting(false);
    if (project) {
      setDropdownOpen(false);
      setCreating(false);
      setNewName("");
      router.push(`/project/${encodeURIComponent(project.project_id)}`);
    }
  };

  return (
    <header
      className="fixed top-0 left-0 right-0 z-[100] flex items-center px-3 gap-2
                 bg-buddy-base border-b border-buddy-border"
      style={{ height: 48 }}
    >

      {/* ── LEFT: Project Switcher ── */}
      <div className="flex items-center flex-1 min-w-0" ref={dropdownRef}>
        <div className="relative">
          <button
            data-testid="project-switcher-btn"
            onClick={() => { setDropdownOpen((o) => !o); setCreating(false); setNewName(""); }}
            className="flex items-center border border-transparent rounded-[8px]
                       hover:bg-buddy-elevated transition-colors"
            style={{ gap: 7, padding: "5px 10px", maxWidth: 200 }}
          >
            {/* Logo mark — 22×22, radius 5 */}
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

            {/* Chevron ▾ */}
            <span className="text-buddy-text-dim shrink-0" style={{ fontSize: 10 }}>▾</span>
          </button>

          {/* Dropdown */}
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
                  const isActive = p.project_id === projectId;
                  return (
                    <div
                      key={p.project_id}
                      className={`flex items-center group/row rounded-[5px] transition-colors
                                  ${isActive ? "bg-buddy-elevated" : "hover:bg-buddy-elevated"}`}
                    >
                      <button
                        onClick={() => handleSelectProject(p.project_id)}
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

      {/* ── CENTER: empty spacer ── */}
      <div className="flex-1" />

      {/* ── RIGHT: RAG badge + panel toggle + avatar ── */}
      <div className="flex items-center gap-2">

        {/* RAG badge with tooltip */}
        {ragReady && (
          <div className="relative group">
            <span
              className="font-bold font-mono tracking-wide
                         bg-buddy-success/15 border border-buddy-success/30 text-buddy-success"
              style={{ padding: "2px 8px", borderRadius: 4, fontSize: 10 }}
            >
              RAG
            </span>
            <span
              className="absolute bottom-[calc(100%+6px)] left-1/2 -translate-x-1/2
                         bg-buddy-surface3 border border-buddy-border-light text-buddy-text
                         whitespace-nowrap pointer-events-none z-[200]
                         hidden group-hover:block"
              style={{ padding: "4px 8px", borderRadius: 4, fontSize: 11 }}
            >
              Kontekst gotowy
            </span>
          </div>
        )}

        {/* Panel toggle */}
        <button
          onClick={onTogglePanel}
          aria-label="Toggle side panel"
          className={`flex items-center justify-center border transition-colors rounded-[6px]
                      ${panelOpen
                        ? "bg-buddy-gold/15 border-buddy-gold/40 text-buddy-gold"
                        : "border-buddy-border text-buddy-text-dim hover:bg-buddy-elevated hover:text-buddy-text-muted"
                      }`}
          style={{ width: 30, height: 30 }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"
               stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="2" width="12" height="12" rx="2" />
            <path d="M10 2v12" />
          </svg>
        </button>

        {/* Avatar with tooltip */}
        <div className="relative group">
          <div
            className="rounded-full border border-buddy-border-light
                       flex items-center justify-center font-bold text-buddy-text-muted
                       select-none cursor-pointer hover:border-buddy-gold hover:text-buddy-gold
                       transition-colors bg-buddy-border"
            style={{ width: 30, height: 30, fontSize: 11 }}
          >
            TK
          </div>
          <span
            className="absolute bottom-[calc(100%+6px)] left-1/2 -translate-x-1/2
                       bg-buddy-border border border-buddy-border-light text-buddy-text
                       whitespace-nowrap pointer-events-none z-[200]
                       hidden group-hover:block"
            style={{ padding: "4px 8px", borderRadius: 4, fontSize: 11 }}
          >
            Tom Kuran
          </span>
        </div>
      </div>
    </header>
  );
}
