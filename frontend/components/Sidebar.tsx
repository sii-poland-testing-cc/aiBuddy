"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { useProjects } from "@/lib/useProjects";
import { useContextStatuses } from "@/lib/useContextStatuses";
import type { ProjectFile } from "@/lib/useProjectFiles";

const MONTHS = [
  "sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru",
];

function formatDate(dateStr?: string) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

const ACCEPTED = ".xlsx,.csv,.json,.pdf,.feature,.txt,.md";

interface SidebarProps {
  activeProjectId: string;
  projectFiles: ProjectFile[];
  onUploadFiles: (files: File[]) => Promise<string[]>;
  isUploading?: boolean;
  contextReady?: boolean;
  activeModule?: "m1" | "requirements" | "m2";
}

export default function Sidebar({
  activeProjectId,
  projectFiles,
  onUploadFiles,
  isUploading,
  contextReady,
  activeModule,
}: SidebarProps) {
  const router = useRouter();
  const { projects, createProject } = useProjects();
  const contextStatuses = useContextStatuses(projects.map((p) => p.project_id));
  const [tab, setTab] = useState<"projects" | "files">("projects");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    const project = await createProject(name);
    if (project) {
      setCreating(false);
      setNewName("");
      router.push(`/chat/${encodeURIComponent(project.project_id)}`);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length) await onUploadFiles(files);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="w-[260px] bg-buddy-surface border-r border-buddy-border flex flex-col shrink-0">
      {/* Logo */}
      <div className="px-[18px] py-5 border-b border-buddy-border flex items-center gap-2.5">
        <div className="w-[30px] h-[30px] rounded-lg bg-gradient-to-br from-buddy-gold to-buddy-gold-light flex items-center justify-center text-sm font-bold text-buddy-surface shrink-0">
          Q
        </div>
        <span className="text-[15px] font-semibold tracking-tight text-buddy-gold-light">
          AI Buddy
        </span>
        <span className="ml-auto text-[10px] bg-buddy-border text-buddy-gold border border-buddy-border-dark font-mono px-1.5 py-0.5 rounded">
          BETA
        </span>
      </div>

      {/* Module switcher */}
      <div className="px-3 py-2.5 border-b border-buddy-border">
        <div className="text-[9px] text-buddy-text-faint uppercase tracking-widest font-semibold mb-2 px-1">
          Modules
        </div>
        {([
          { id: "m1",           icon: "🧠", label: "Context Builder",       path: `/context/${encodeURIComponent(activeProjectId)}`,      locked: false          },
          { id: "requirements", icon: "📋", label: "Requirements",           path: `/requirements/${encodeURIComponent(activeProjectId)}`, locked: !contextReady },
          { id: "m2",           icon: "🔍", label: "Suite Analyzer",         path: `/chat/${encodeURIComponent(activeProjectId)}`,         locked: !contextReady },
        ] as const).map((m) => {
          const isActive = activeModule === m.id;
          return (
            <button
              key={m.id}
              onClick={() => !m.locked && router.push(m.path)}
              disabled={m.locked}
              className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-left transition-all mb-1 border-l-2 ${
                isActive
                  ? "bg-buddy-border border-buddy-gold"
                  : "border-transparent hover:bg-buddy-border/40"
              } ${m.locked ? "opacity-40 cursor-default" : "cursor-pointer"}`}
            >
              <span className="text-sm leading-none">{m.icon}</span>
              <span className={`text-xs font-medium ${isActive ? "text-buddy-gold-light" : "text-buddy-text-muted"}`}>
                {m.label}
              </span>
              {!m.locked && contextReady && m.id === "m1" && (
                <span className="ml-auto text-[10px] text-emerald-400">✓</span>
              )}
              {m.locked && <span className="ml-auto text-[10px]">🔒</span>}
            </button>
          );
        })}
      </div>

      {/* Tabs */}
      <div className="flex px-3 pt-2.5 gap-1">
        {(["projects", "files"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-1.5 text-xs font-medium uppercase tracking-wide border-b-2 transition-colors ${
              tab === t
                ? "border-buddy-gold text-buddy-gold-light"
                : "border-transparent text-buddy-text-muted hover:text-buddy-gold-light"
            }`}
          >
            {t === "projects" ? "Projekty" : "Pliki"}
          </button>
        ))}
      </div>

      {tab === "projects" ? (
        <>
          {/* New project button / inline form */}
          <div className="px-3 pt-3 pb-1">
            {creating ? (
              <form onSubmit={handleCreate} className="flex gap-1.5">
                <input
                  autoFocus
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Nazwa projektu"
                  onKeyDown={(e) => e.key === "Escape" && setCreating(false)}
                  className="flex-1 text-xs bg-buddy-elevated border border-buddy-border-dark rounded-lg px-2.5 py-1.5 text-buddy-text placeholder:text-buddy-text-muted focus:outline-none focus:border-buddy-gold"
                />
                <button
                  type="submit"
                  className="px-2.5 py-1 text-xs bg-gradient-to-r from-buddy-gold to-buddy-gold-light text-buddy-surface rounded-lg font-semibold"
                >
                  ✓
                </button>
              </form>
            ) : (
              <button
                onClick={() => setCreating(true)}
                className="w-full px-3 py-2 bg-gradient-to-r from-buddy-gold to-buddy-gold-light text-buddy-surface rounded-lg text-sm font-semibold flex items-center gap-1.5 hover:opacity-90 transition-opacity"
              >
                <span className="text-base leading-none">+</span> Nowy projekt
              </button>
            )}
          </div>

          {/* Project list */}
          <div className="flex-1 overflow-y-auto py-1">
            {projects.length > 0 && (
              <div className="px-3.5 py-2 text-[10px] text-buddy-text-faint uppercase tracking-widest font-semibold">
                Ostatnie
              </div>
            )}
            {projects.map((p) => {
              const isActive = p.project_id === activeProjectId;
              // Prefer live prop for the active project (most up-to-date), batch fetch for others
              const hasContext = isActive
                ? (contextReady ?? contextStatuses[p.project_id] ?? false)
                : (contextStatuses[p.project_id] ?? false);
              return (
                <div key={p.project_id}>
                  <button
                    onClick={() =>
                      router.push(`/chat/${encodeURIComponent(p.project_id)}`)
                    }
                    className={`w-full text-left px-4 py-2.5 border-l-2 transition-all ${
                      isActive
                        ? "bg-buddy-border border-buddy-gold"
                        : "border-transparent hover:bg-buddy-border/50"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-buddy-text truncate flex-1">
                        {p.name}
                      </span>
                      {hasContext ? (
                        <span style={{ color: "#4a9e6b", fontSize: 10 }} title="Context ready">●</span>
                      ) : (
                        <span className="w-1.5 h-1.5 rounded-full bg-buddy-border-dark shrink-0" title="No context" />
                      )}
                    </div>
                    <div className="text-[11px] text-buddy-text-dim flex gap-2 mt-0.5">
                      {p.files !== undefined && (
                        <span>📄 {p.files.length} pliki</span>
                      )}
                      {p.created_at && <span>· {formatDate(p.created_at)}</span>}
                    </div>
                  </button>

                  {/* Context Builder shortcut for active project */}
                  {isActive && (
                    <button
                      onClick={() =>
                        router.push(`/context/${encodeURIComponent(p.project_id)}`)
                      }
                      className="w-full text-left pl-8 pr-4 py-1.5 flex items-center gap-1.5 hover:bg-buddy-border/30 transition-colors"
                    >
                      <span className={`text-[10px] font-mono ${hasContext ? "text-emerald-400" : "text-buddy-text-faint"}`}>
                        {hasContext ? "✓" : "○"}
                      </span>
                      <span className="text-[11px] text-buddy-text-faint hover:text-buddy-text-dim transition-colors">
                        Context Builder
                      </span>
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {/* Upload zone */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="w-full px-3 py-7 bg-buddy-elevated border-2 border-dashed border-buddy-border-dark rounded-xl text-buddy-text-muted text-sm text-center leading-relaxed hover:border-buddy-muted transition-colors disabled:opacity-60"
          >
            <div className="text-2xl mb-1.5">📁</div>
            {isUploading ? "Przesyłanie…" : "Wgraj pliki do projektu"}
            <div className="text-[11px] mt-1 text-buddy-text-faint">
              .xlsx .csv .json .pdf
            </div>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED}
            className="hidden"
            onChange={handleFileChange}
          />

          {/* Uploaded file list */}
          {projectFiles.map((f, i) => {
            const ext = f.filename.split(".").pop()?.toUpperCase() ?? "FILE";
            return (
              <div
                key={i}
                className="flex items-center gap-2 px-2.5 py-2 bg-buddy-elevated rounded-md border border-buddy-border text-xs"
              >
                <span className="font-mono text-buddy-gold opacity-60">
                  {ext}
                </span>
                <span className="text-buddy-text flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-mono">
                  {f.filename}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* User footer */}
      <div className="px-4 py-3 border-t border-buddy-border flex items-center gap-2.5 text-sm">
        <div className="w-7 h-7 rounded-full bg-buddy-border-dark flex items-center justify-center text-xs font-semibold text-buddy-gold shrink-0">
          TK
        </div>
        <span className="text-buddy-text-muted">Tom K.</span>
        <span className="ml-auto text-[10px] text-buddy-text-faint bg-buddy-elevated border border-buddy-border px-1.5 py-0.5 rounded">
          PRO
        </span>
      </div>
    </div>
  );
}
