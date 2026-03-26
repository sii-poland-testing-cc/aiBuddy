"use client";

import { useState } from "react";
import { PanelCard } from "./PanelCard";
import type { PanelFile } from "../lib/types";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface JiraItem {
  id: string;
  key: string;
}

// ── File extension helpers ─────────────────────────────────────────────────────

const EXT_COLORS: Record<string, { bg: string; color: string }> = {
  xlsx: { bg: "rgba(74,158,107,0.2)",   color: "#4a9e6b" },
  csv:  { bg: "rgba(74,158,107,0.15)",  color: "#6dc28a" },
  feature: { bg: "rgba(155,107,191,0.2)", color: "#b07fe0" },
  docx: { bg: "rgba(91,127,186,0.2)",   color: "#5b7fba" },
  pdf:  { bg: "rgba(192,80,74,0.15)",   color: "#e08080" },
};

function fileExtLabel(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    xlsx: "XLS", csv: "CSV", feature: "FT",
    docx: "DOC", pdf: "PDF", json: "JSON",
    md: "MD", txt: "TXT",
  };
  return map[ext] ?? ext.toUpperCase().slice(0, 4);
}

function fileExtStyle(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return EXT_COLORS[ext] ?? { bg: "var(--bg)", color: "var(--text-dim)" };
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="font-semibold uppercase text-buddy-text-dim"
      style={{ fontSize: 10, letterSpacing: "0.06em", padding: "6px 0 4px", marginTop: 4 }}
    >
      {children}
    </div>
  );
}

function FileList({
  files,
  isNew,
  onFileToggle,
  onDeleteFile,
}: {
  files: PanelFile[];
  isNew: boolean;
  onFileToggle?: (filePath: string, checked: boolean) => void;
  onDeleteFile?: (id: string) => void;
}) {
  return (
    <div className="flex flex-col">
      {files.map((f) => {
        const extStyle = fileExtStyle(f.filename);
        const label = fileExtLabel(f.filename);
        const isAlwaysOn = f.source_type !== "file";
        const isPending = f.isNew === true && f.id.startsWith("pending-");
        return (
          <div
            key={f.id}
            className="flex items-center border-b border-buddy-border/50 group"
            style={{ gap: 7, padding: "5px 0", opacity: isNew ? 1 : 0.5 }}
          >
            <input
              type="checkbox"
              defaultChecked={f.selected}
              disabled={isAlwaysOn}
              style={{ accentColor: "#c8902a", cursor: isAlwaysOn ? "not-allowed" : "pointer" }}
              onChange={(e) => onFileToggle?.(f.file_path, e.target.checked)}
            />
            <div
              className="flex items-center justify-center font-mono font-bold shrink-0"
              style={{
                width: 20, height: 20, borderRadius: 3,
                fontSize: 8,
                background: extStyle.bg,
                color: extStyle.color,
              }}
            >
              {label}
            </div>
            <span
              className="text-buddy-text-muted flex-1 overflow-hidden"
              style={{ fontSize: 11, textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {f.filename}
            </span>
            {isNew && (
              <span className="font-mono font-bold text-buddy-success" style={{ fontSize: 9 }}>
                NEW
              </span>
            )}
            {!isPending && onDeleteFile && (
              <button
                data-testid="file-delete-btn"
                onClick={() => {
                  if (window.confirm("Usunąć plik " + f.filename + "?")) {
                    onDeleteFile(f.id);
                  }
                }}
                title="Usuń"
                className="opacity-0 group-hover:opacity-100 text-buddy-text-dim hover:text-red-400 transition-all"
                style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, padding: "0 2px", lineHeight: 1 }}
              >
                ✕
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

function AddButton({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full mt-2 border border-dashed border-buddy-border text-buddy-text-dim hover:border-buddy-gold hover:text-buddy-gold-light transition-colors"
      style={{ padding: "5px 10px", borderRadius: 5, fontSize: 11, background: "none", cursor: "pointer" }}
    >
      {children}
    </button>
  );
}

// ── SourcesCard ────────────────────────────────────────────────────────────────

export function SourcesCard({
  cardId,
  auditFiles = [],
  onAddFiles,
  onFileToggle,
  onDeleteFile,
  jiraItems = [],
  onAddJira,
  onDeleteJira,
  jiraConfigured = true,
}: {
  cardId: string;
  auditFiles: PanelFile[];
  onAddFiles?: () => void;
  onFileToggle?: (filePath: string, checked: boolean) => void;
  onDeleteFile?: (id: string) => void;
  jiraItems?: JiraItem[];
  onAddJira?: (key: string) => Promise<void>;
  onDeleteJira?: (id: string) => void;
  jiraConfigured?: boolean;
}) {
  const [activeTab, setActiveTab] = useState<"files" | "jira" | "links">("files");
  const [jiraInput, setJiraInput] = useState("");
  const [jiraLoading, setJiraLoading] = useState(false);
  const [jiraError, setJiraError] = useState<string | null>(null);

  const newFiles  = auditFiles.filter((f) => f.source_type === "file" && f.isNew);
  const usedFiles = auditFiles.filter((f) => f.source_type === "file" && !f.isNew);
  // Links = only url + confluence (jira has its own tab)
  const links = auditFiles.filter(
    (f) => f.source_type === "url" || f.source_type === "confluence"
  );

  const linkBadgeStyle = (type: string) => {
    if (type === "confluence") return { bg: "rgba(91,127,186,0.2)", color: "#5b7fba" };
    return { bg: "var(--surface3)", color: "var(--text-dim)" };
  };

  const handleAddJira = async () => {
    const key = jiraInput.trim().toUpperCase();
    if (!key || !onAddJira) return;
    setJiraLoading(true);
    setJiraError(null);
    try {
      await onAddJira(key);
      setJiraInput("");
    } catch (e: unknown) {
      setJiraError(e instanceof Error ? e.message : "Błąd podczas dodawania");
    } finally {
      setJiraLoading(false);
    }
  };

  return (
    <PanelCard id={cardId} icon="📎" title="Źródła" defaultOpen>
      {/* Tabs */}
      <div
        className="flex bg-buddy-base"
        style={{ gap: 2, marginBottom: 8, borderRadius: 4, padding: 2 }}
      >
        {(["files", "jira", "links"] as const).map((tab) => (
          <button
            key={tab}
            data-testid={`src-tab-${tab}`}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 transition-colors ${
              activeTab === tab
                ? "bg-buddy-surface2 border border-buddy-border text-buddy-text-muted"
                : "border border-transparent text-buddy-text-dim hover:text-buddy-text-muted"
            }`}
            style={{ padding: "4px 6px", borderRadius: 4, fontSize: 11, cursor: "pointer" }}
          >
            {tab === "files" ? "Pliki" : tab === "jira" ? "Jira" : "Linki"}
          </button>
        ))}
      </div>

      {/* Files tab */}
      {activeTab === "files" && (
        <div>
          {newFiles.length > 0 && (
            <>
              <SectionLabel>Nowe</SectionLabel>
              <FileList files={newFiles} isNew onFileToggle={onFileToggle} onDeleteFile={onDeleteFile} />
            </>
          )}
          {usedFiles.length > 0 && (
            <>
              <SectionLabel>Poprzednio użyte</SectionLabel>
              <FileList files={usedFiles} isNew={false} onFileToggle={onFileToggle} onDeleteFile={onDeleteFile} />
            </>
          )}
          {auditFiles.filter((f) => f.source_type === "file").length === 0 && (
            <p className="text-buddy-text-faint" style={{ fontSize: 11, textAlign: "center", padding: "8px 0" }}>
              Brak plików
            </p>
          )}
          <AddButton onClick={onAddFiles}>+ Dodaj pliki</AddButton>
        </div>
      )}

      {/* Jira tab */}
      {activeTab === "jira" && (
        <div>
          {!jiraConfigured && (
            <div
              data-testid="jira-config-overlay"
              className="text-buddy-text-dim"
              style={{ fontSize: 11, padding: "10px 0", textAlign: "center", lineHeight: 1.5 }}
            >
              Skonfiguruj Jira w ustawieniach projektu,<br />
              aby dodawać issues jako źródła.
            </div>
          )}
          {jiraConfigured && (
          <>
          {/* Input + plus icon button */}
          <div style={{ display: "flex", gap: 6, marginBottom: jiraError ? 4 : 8 }}>
            <input
              type="text"
              placeholder="np. PROJ-123"
              value={jiraInput}
              onChange={(e) => { setJiraInput(e.target.value); setJiraError(null); }}
              onKeyDown={(e) => { if (e.key === "Enter") handleAddJira(); }}
              disabled={jiraLoading}
              data-testid="jira-issue-input"
              className="flex-1 bg-buddy-surface2 border border-buddy-border text-buddy-text placeholder:text-buddy-text-dim focus:outline-none focus:border-buddy-gold transition-colors"
              style={{ padding: "5px 8px", borderRadius: 4, fontSize: 11 }}
            />
            <button
              onClick={handleAddJira}
              disabled={jiraLoading || !jiraInput.trim()}
              title="Dodaj Jira issue"
              data-testid="jira-add-btn"
              className="border border-buddy-border text-buddy-text-dim hover:border-buddy-gold hover:text-buddy-gold-light disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              style={{
                width: 28, height: 28, borderRadius: 4,
                background: "none", cursor: "pointer", flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 18, lineHeight: 1,
              }}
            >
              {jiraLoading ? "…" : "+"}
            </button>
          </div>
          {jiraError && (
            <p style={{ fontSize: 10, color: "#e08080", marginBottom: 6, lineHeight: 1.4 }}>
              {jiraError}
            </p>
          )}
          {jiraItems.length > 0 ? (
            <div className="flex flex-col">
              {jiraItems.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center gap-2 border-b border-buddy-border group"
                  style={{ padding: "5px 0" }}
                >
                  <span
                    className="font-mono font-bold shrink-0"
                    style={{
                      fontSize: 9, padding: "1px 5px", borderRadius: 3,
                      background: "rgba(74,158,107,0.15)", color: "#6dc28a",
                    }}
                  >
                    JIRA
                  </span>
                  <span
                    className="font-mono text-buddy-text-muted flex-1 overflow-hidden"
                    style={{ fontSize: 10, textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  >
                    {item.key}
                  </span>
                  {onDeleteJira && (
                    <button
                      data-testid="jira-delete-btn"
                      onClick={() => {
                        if (window.confirm("Usunąć issue " + item.key + "?")) {
                          onDeleteJira(item.id);
                        }
                      }}
                      title="Usuń"
                      className="opacity-0 group-hover:opacity-100 text-buddy-text-dim hover:text-red-400 transition-all"
                      style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, padding: "0 2px", lineHeight: 1 }}
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-buddy-text-faint" style={{ fontSize: 11, textAlign: "center", padding: "8px 0" }}>
              Brak issues Jira
            </p>
          )}
          </>
          )}
        </div>
      )}

      {/* Links tab */}
      {activeTab === "links" && (
        <div>
          {links.length > 0 ? (
            <div className="flex flex-col">
              {links.map((f) => {
                const style = linkBadgeStyle(f.source_type);
                const label = f.source_type === "confluence" ? "CONF" : "URL";
                return (
                  <div
                    key={f.id}
                    className="flex items-center gap-2 border-b border-buddy-border"
                    style={{ padding: "5px 0" }}
                  >
                    <input
                      type="checkbox"
                      defaultChecked={f.selected}
                      style={{ accentColor: "#c8902a", cursor: "pointer" }}
                      onChange={(e) => onFileToggle?.(f.file_path, e.target.checked)}
                    />
                    <span
                      className="font-mono font-bold shrink-0"
                      style={{
                        fontSize: 9, padding: "1px 5px", borderRadius: 3,
                        background: style.bg, color: style.color,
                      }}
                    >
                      {label}
                    </span>
                    <span
                      className="font-mono text-buddy-text-muted flex-1 overflow-hidden"
                      style={{ fontSize: 10, textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                    >
                      {f.filename}
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-buddy-text-faint" style={{ fontSize: 11, textAlign: "center", padding: "8px 0" }}>
              Brak linków
            </p>
          )}
          <AddButton onClick={onAddFiles}>+ Dodaj link</AddButton>
        </div>
      )}
    </PanelCard>
  );
}
