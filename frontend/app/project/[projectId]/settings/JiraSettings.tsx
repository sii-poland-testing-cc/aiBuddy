"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const INPUT_CLS =
  "bg-buddy-elevated border border-buddy-border rounded-lg px-4 py-2.5 text-sm text-buddy-text placeholder:text-buddy-text-faint focus:outline-none focus:border-buddy-gold transition-colors";

const LABEL_CLS =
  "text-xs font-semibold uppercase tracking-widest text-buddy-text-muted";

interface JiraSettingsProps {
  projectId: string;
  jiraUrl: string;
  jiraUserEmail: string;
  jiraApiKey: string;
  onJiraUrlChange: (v: string) => void;
  onJiraUserEmailChange: (v: string) => void;
  onJiraApiKeyChange: (v: string) => void;
}

export default function JiraSettings({
  projectId,
  jiraUrl,
  jiraUserEmail,
  jiraApiKey,
  onJiraUrlChange,
  onJiraUserEmailChange,
  onJiraApiKeyChange,
}: JiraSettingsProps) {
  const [testResult, setTestResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const [testing, setTesting] = useState(false);

  const handleTest = async () => {
    if (testing) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch(
        `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/settings/test-jira`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jira_url: jiraUrl.trim(),
            jira_user_email: jiraUserEmail.trim(),
            jira_api_key: jiraApiKey.trim(),
          }),
        }
      );
      const data = await res.json();
      setTestResult({ ok: data.ok, detail: data.detail });
    } catch {
      setTestResult({ ok: false, detail: "Błąd połączenia z serwerem." });
    } finally {
      setTesting(false);
    }
  };

  const canTest = jiraUrl.trim() && jiraUserEmail.trim() && jiraApiKey.trim();

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <label className={LABEL_CLS}>Adres serwera Jira</label>
        <input
          value={jiraUrl}
          onChange={(e) => { onJiraUrlChange(e.target.value); setTestResult(null); }}
          className={INPUT_CLS}
          placeholder="https://twoja-firma.atlassian.net"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className={LABEL_CLS}>Jira — adres e-mail użytkownika</label>
        <input
          value={jiraUserEmail}
          onChange={(e) => { onJiraUserEmailChange(e.target.value); setTestResult(null); }}
          className={INPUT_CLS}
          placeholder="uzytkownik@firma.com"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className={LABEL_CLS}>Jira API Key</label>
        <input
          type="password"
          value={jiraApiKey}
          onChange={(e) => { onJiraApiKeyChange(e.target.value); setTestResult(null); }}
          className={INPUT_CLS}
          placeholder="API key lub token dostępu"
        />
      </div>

      {canTest && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleTest}
            disabled={testing}
            className="px-4 py-2 border border-buddy-border rounded-lg text-sm text-buddy-text-muted hover:border-buddy-gold hover:text-buddy-gold-light disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            {testing ? "Testowanie…" : "Testuj połączenie Jira"}
          </button>
          {testResult && (
            <span className={`text-xs ${testResult.ok ? "text-buddy-success" : "text-red-400"}`}>
              {testResult.ok ? "✓" : "✗"} {testResult.detail}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
