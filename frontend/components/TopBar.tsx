"use client";

import { useProjects } from "../lib/useProjects";
import { useContextStatuses } from "../lib/useContextStatuses";
import { ProjectSwitcherDropdown } from "./ProjectSwitcherDropdown";

interface TopBarProps {
  projectId: string;
  onTogglePanel: () => void;
  panelOpen: boolean;
  ragReady: boolean;
}

export default function TopBar({ projectId, onTogglePanel, panelOpen, ragReady }: TopBarProps) {
  const { projects, createProject } = useProjects();
  const statuses = useContextStatuses(projects.map((p) => p.project_id));

  return (
    <header
      className="fixed top-0 left-0 right-0 z-[100] flex items-center px-3 gap-2
                 bg-buddy-base border-b border-buddy-border"
      style={{ height: 48 }}
    >

      {/* ── LEFT: Project Switcher ── */}
      <ProjectSwitcherDropdown
        projects={projects}
        currentProjectId={projectId}
        statuses={statuses}
        onCreateProject={createProject}
      />

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
