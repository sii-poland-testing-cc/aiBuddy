"use client";

import { useRouter } from "next/navigation";
import { useProjects } from "../lib/useProjects";
import { useContextStatuses } from "../lib/useContextStatuses";
import { ProjectSwitcherDropdown } from "./ProjectSwitcherDropdown";
import { useCurrentUser } from "../lib/useCurrentUser";
import { apiFetch } from "../lib/apiFetch";

function getInitials(email: string): string {
  const local = email.split("@")[0];
  const parts = local.split(/[._-]/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return local.slice(0, 2).toUpperCase();
}

interface TopBarProps {
  projectId: string;
  onTogglePanel: () => void;
  panelOpen: boolean;
  ragReady: boolean;
}

export default function TopBar({ projectId, onTogglePanel, panelOpen, ragReady }: TopBarProps) {
  const { projects, createProject } = useProjects();
  const statuses = useContextStatuses(projects.map((p) => p.project_id));
  const { user } = useCurrentUser();
  const router = useRouter();

  async function handleLogout() {
    await apiFetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  const initials = user ? getInitials(user.email) : "??";

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
                         bg-buddy-elevated border border-buddy-border-dark text-buddy-text
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

        {/* Avatar with dropdown */}
        <div className="relative group">
          <div
            className="rounded-full border border-buddy-border-light
                       flex items-center justify-center font-bold text-buddy-text-muted
                       select-none cursor-pointer hover:border-buddy-gold hover:text-buddy-gold
                       transition-colors bg-buddy-border"
            style={{ width: 30, height: 30, fontSize: 11 }}
          >
            {initials}
          </div>

          {/* Dropdown — appears on hover; pt-1.5 bridges gap without breaking hover zone */}
          <div
            className="absolute right-0 top-full pt-1.5
                       pointer-events-none opacity-0
                       group-hover:pointer-events-auto group-hover:opacity-100
                       transition-opacity z-[200]"
            style={{ minWidth: 180 }}
          >
          <div className="bg-buddy-elevated border border-buddy-border-dark rounded-[6px] shadow-lg">
            {/* User email */}
            <div
              className="px-3 py-2 text-buddy-text-dim border-b border-buddy-border"
              style={{ fontSize: 11 }}
            >
              {user?.email ?? "…"}
            </div>

            {/* Profile link */}
            <a
              href="/profile"
              className="flex items-center gap-2 px-3 py-2 text-buddy-text-muted
                         hover:bg-buddy-elevated hover:text-buddy-text transition-colors"
              style={{ fontSize: 12 }}
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none"
                   stroke="currentColor" strokeWidth="1.5">
                <circle cx="8" cy="5" r="3" />
                <path d="M2 14c0-3.314 2.686-5 6-5s6 1.686 6 5" />
              </svg>
              Profil
            </a>

            {/* Divider */}
            <div className="border-t border-buddy-border" />

            {/* Logout */}
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-2 px-3 py-2 text-buddy-text-muted
                         hover:bg-buddy-elevated hover:text-buddy-error transition-colors
                         text-left"
              style={{ fontSize: 12 }}
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none"
                   stroke="currentColor" strokeWidth="1.5">
                <path d="M6 3H3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h3" />
                <path d="M10 11l3-3-3-3M13 8H6" />
              </svg>
              Wyloguj
            </button>
          </div>{/* inner card */}
          </div>{/* outer hover bridge */}
        </div>
      </div>
    </header>
  );
}
