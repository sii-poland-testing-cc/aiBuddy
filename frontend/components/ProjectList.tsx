"use client";

import { useRouter } from "next/navigation";

interface Project {
  project_id: string;
  name: string;
  created_at?: string;
}

interface ProjectListProps {
  projects: Project[];
  runningProjects: Set<string>;
  statuses: Record<string, boolean>;
  formatDate: (iso?: string) => string;
}

export default function ProjectList({
  projects,
  runningProjects,
  statuses,
  formatDate,
}: ProjectListProps) {
  const router = useRouter();

  return (
    <div className="flex flex-col gap-0.5 mb-6">
      {projects.map((p) => (
        <div key={p.project_id} className="flex items-center group rounded-lg hover:bg-buddy-elevated transition-colors">
          <button
            onClick={() => router.push(`/chat/${encodeURIComponent(p.project_id)}`)}
            className="flex-1 flex items-center gap-3 px-4 py-3 text-left min-w-0"
          >
            <div className={`w-2 h-2 rounded-full shrink-0 transition-colors ${
              runningProjects.has(p.project_id)
                ? "bg-buddy-gold animate-pulse"
                : statuses[p.project_id]
                  ? "bg-buddy-success"
                  : "bg-buddy-border-dark"
            }`} />
            <div className="flex-1 min-w-0">
              <span className="block text-sm font-medium text-buddy-text group-hover:text-buddy-gold-light transition-colors truncate">
                {p.name}
              </span>
              {p.created_at && (
                <span className="block text-xs text-buddy-text-dim mt-0.5">
                  {formatDate(p.created_at)}
                </span>
              )}
            </div>
            <span className="text-buddy-text-faint opacity-0 group-hover:opacity-100 transition-opacity">
              →
            </span>
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              router.push(`/project/${encodeURIComponent(p.project_id)}/settings`);
            }}
            title="Ustawienia projektu"
            className="shrink-0 px-3 py-3 text-buddy-text-dim opacity-0 group-hover:opacity-100 hover:text-buddy-gold-light transition-all"
            style={{ fontSize: 14 }}
          >
            ⚙
          </button>
        </div>
      ))}

      {projects.length === 0 && (
        <p className="text-center text-xs text-buddy-text-dim py-4">
          Brak projektów — utwórz pierwszy poniżej.
        </p>
      )}
    </div>
  );
}
