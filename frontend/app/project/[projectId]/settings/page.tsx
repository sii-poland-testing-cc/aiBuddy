"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import JiraSettings from "./JiraSettings";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ProjectSettings {
  name?: string;
  description?: string;
  [key: string]: unknown;
}

interface Project {
  project_id: string;
  name: string;
  description: string;
}

export default function ProjectSettingsPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = params?.projectId as string;

  const [project, setProject] = useState<Project | null>(null);
  const [settings, setSettings] = useState<ProjectSettings>({});
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [jiraUrl, setJiraUrl] = useState("");
  const [jiraUserEmail, setJiraUserEmail] = useState("");
  const [jiraApiKey, setJiraApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [projRes, settingsRes] = await Promise.all([
        fetch(`${API_BASE}/api/projects/${encodeURIComponent(projectId)}`),
        fetch(`${API_BASE}/api/projects/${encodeURIComponent(projectId)}/settings`),
      ]);
      if (!projRes.ok) { setError("Nie znaleziono projektu."); setLoading(false); return; }
      const proj: Project = await projRes.json();
      const s: ProjectSettings = settingsRes.ok ? await settingsRes.json() : {};
      setProject(proj);
      setName((s.name as string) || proj.name);
      setDescription((s.description as string) ?? proj.description ?? "");
      setJiraUrl((s.jira_url as string) ?? "");
      setJiraUserEmail((s.jira_user_email as string) ?? "");
      setJiraApiKey((s.jira_api_key as string) ?? "");
      setSettings(s);
    } catch {
      setError("Błąd połączenia z serwerem.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || saving) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const payload: ProjectSettings = {
        ...settings,
        name: name.trim(),
        description: description.trim(),
        jira_url: jiraUrl.trim(),
        jira_user_email: jiraUserEmail.trim(),
        jira_api_key: jiraApiKey.trim(),
      };
      const res = await fetch(
        `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/settings`,
        { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }
      );
      if (!res.ok) throw new Error("save failed");
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch {
      setError("Nie udało się zapisać ustawień.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-buddy-base">
        <span className="text-buddy-text-dim text-sm">Ładowanie…</span>
      </main>
    );
  }

  if (error && !project) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-buddy-base">
        <div className="text-center">
          <p className="text-buddy-text-dim text-sm mb-4">{error}</p>
          <button onClick={() => router.push("/")} className="text-buddy-gold text-sm hover:underline">
            ← Wróć do listy projektów
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-buddy-base p-8">
      <div className="w-full max-w-[480px]">

        {/* Header */}
        <div className="mb-8">
          <button
            onClick={() => router.push(`/project/${encodeURIComponent(projectId)}`)}
            className="text-xs text-buddy-text-dim hover:text-buddy-gold-light transition-colors mb-4 inline-flex items-center gap-1"
          >
            ← Wróć do projektu
          </button>
          <h1 className="text-lg font-semibold text-buddy-text">Ustawienia projektu</h1>
          <p className="text-xs text-buddy-text-dim mt-1 font-mono truncate">{projectId}</p>
        </div>

        <form onSubmit={handleSave} className="flex flex-col gap-5">

          {/* Name */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold uppercase tracking-widest text-buddy-text-muted">
              Nazwa projektu
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="bg-buddy-elevated border border-buddy-border rounded-lg px-4 py-2.5 text-sm text-buddy-text placeholder:text-buddy-text-faint focus:outline-none focus:border-buddy-gold transition-colors"
              placeholder="Nazwa projektu"
            />
          </div>

          {/* Description */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold uppercase tracking-widest text-buddy-text-muted">
              Opis
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="bg-buddy-elevated border border-buddy-border rounded-lg px-4 py-2.5 text-sm text-buddy-text placeholder:text-buddy-text-faint focus:outline-none focus:border-buddy-gold transition-colors resize-none"
              placeholder="Krótki opis projektu (opcjonalnie)"
            />
          </div>

          {/* Divider */}
          <div className="border-t border-buddy-border" />

          {/* Jira */}
          <JiraSettings
            projectId={projectId}
            jiraUrl={jiraUrl}
            jiraUserEmail={jiraUserEmail}
            jiraApiKey={jiraApiKey}
            onJiraUrlChange={setJiraUrl}
            onJiraUserEmailChange={setJiraUserEmail}
            onJiraApiKeyChange={setJiraApiKey}
          />

          {/* Divider */}
          <div className="border-t border-buddy-border" />

          {/* Error / success */}
          {error && (
            <p className="text-xs text-red-400">{error}</p>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={saving || !name.trim()}
              className="px-5 py-2.5 bg-buddy-gold rounded-lg text-sm font-medium text-buddy-surface hover:bg-buddy-gold-light disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              {saving ? "Zapisywanie…" : "Zapisz ustawienia"}
            </button>
            {saved && (
              <span className="text-xs text-buddy-success">Zapisano</span>
            )}
          </div>

        </form>
      </div>
    </main>
  );
}
