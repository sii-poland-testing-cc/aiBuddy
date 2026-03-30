"use client";

import { useState, useEffect, useCallback, useMemo } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Mode = "context" | "requirements" | "audit";

interface JiraSource {
  key: string;
  indexed: boolean;
  indexed_at: string | null;
}

interface UseJiraOptions {
  projectId: string;
  activeMode: Mode;
  jiraSources?: JiraSource[];
  fetchStatus: () => Promise<void> | void;
  onFilesChanged: () => void;
}

export interface UseJiraResult {
  projectSettings: { jira_url?: string; jira_api_key?: string };
  contextJiraItems: { id: string; key: string }[];
  addJiraIssue: (issueKey: string) => Promise<void>;
  deleteJiraIssue: (id: string) => Promise<void>;
  deleteFile: (fileId: string) => Promise<void>;
}

export function useJira({
  projectId,
  activeMode,
  jiraSources,
  fetchStatus,
  onFilesChanged,
}: UseJiraOptions): UseJiraResult {
  const [projectSettings, setProjectSettings] = useState<{
    jira_url?: string;
    jira_api_key?: string;
  }>({});

  useEffect(() => {
    fetch(`${API_BASE}/api/projects/${encodeURIComponent(projectId)}/settings`)
      .then((r) => (r.ok ? r.json() : {}))
      .then((s) => setProjectSettings(s))
      .catch(() => {});
  }, [projectId]);

  const contextJiraItems = useMemo(
    () => (jiraSources ?? []).map((j) => ({ id: `jira:${j.key}`, key: j.key })),
    [jiraSources]
  );

  const addJiraIssue = useCallback(
    async (issueKey: string) => {
      const endpoint =
        activeMode === "context"
          ? `${API_BASE}/api/context/${projectId}/jira`
          : `${API_BASE}/api/files/${projectId}/jira`;
      const resp = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ issue_key: issueKey }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(
          (err as { detail?: string }).detail ?? "Błąd podczas dodawania Jira"
        );
      }
      if (activeMode === "context") {
        await fetchStatus();
      } else {
        onFilesChanged();
      }
    },
    [activeMode, projectId, fetchStatus, onFilesChanged]
  );

  const deleteJiraIssue = useCallback(
    async (id: string) => {
      if (activeMode === "context") {
        const key = id.startsWith("jira:") ? id.slice(5) : id;
        const resp = await fetch(
          `${API_BASE}/api/context/${projectId}/jira/${encodeURIComponent(key)}`,
          { method: "DELETE" }
        );
        if (!resp.ok && resp.status !== 204) {
          const err = await resp.json().catch(() => ({}));
          throw new Error((err as { detail?: string }).detail ?? "Błąd podczas usuwania Jira");
        }
        await fetchStatus();
        return;
      }
      const resp = await fetch(`${API_BASE}/api/files/${projectId}/${id}`, {
        method: "DELETE",
      });
      if (!resp.ok && resp.status !== 204) {
        const err = await resp.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail ?? "Błąd podczas usuwania pliku");
      }
      onFilesChanged();
    },
    [activeMode, projectId, fetchStatus, onFilesChanged]
  );

  const deleteFile = useCallback(
    async (fileId: string) => {
      if (activeMode === "context") {
        const resp = await fetch(
          `${API_BASE}/api/context/${projectId}/docs/${encodeURIComponent(fileId)}`,
          { method: "DELETE" }
        );
        if (!resp.ok && resp.status !== 204) {
          const err = await resp.json().catch(() => ({}));
          throw new Error((err as { detail?: string }).detail ?? "Błąd podczas usuwania pliku");
        }
        await fetchStatus();
        return;
      }
      const resp = await fetch(`${API_BASE}/api/files/${projectId}/${fileId}`, {
        method: "DELETE",
      });
      if (!resp.ok && resp.status !== 204) {
        const err = await resp.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail ?? "Błąd podczas usuwania pliku");
      }
      onFilesChanged();
    },
    [activeMode, projectId, fetchStatus, onFilesChanged]
  );

  return {
    projectSettings,
    contextJiraItems,
    addJiraIssue,
    deleteJiraIssue,
    deleteFile,
  };
}
