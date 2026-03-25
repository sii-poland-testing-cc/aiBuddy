"use client";

import { useState } from "react";
import { PanelCard } from "./PanelCard";
import type { PanelFile } from "../lib/types";

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
}: {
  files: PanelFile[];
  isNew: boolean;
  onFileToggle?: (filePath: string, checked: boolean) => void;
}) {
  return (
    <div className="flex flex-col">
      {files.map((f) => {
        const extStyle = fileExtStyle(f.filename);
        const label = fileExtLabel(f.filename);
        const isAlwaysOn = f.source_type !== "file";
        return (
          <div
            key={f.id}
            className="flex items-center border-b border-buddy-border/50"
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
}: {
  cardId: string;
  auditFiles: PanelFile[];
  onAddFiles?: () => void;
  onFileToggle?: (filePath: string, checked: boolean) => void;
}) {
  const [activeTab, setActiveTab] = useState<"files" | "links">("files");

  const newFiles  = auditFiles.filter((f) => f.source_type === "file" && f.isNew);
  const usedFiles = auditFiles.filter((f) => f.source_type === "file" && !f.isNew);
  const links     = auditFiles.filter((f) => f.source_type !== "file");

  const linkBadgeStyle = (type: string) => {
    if (type === "confluence") return { bg: "rgba(91,127,186,0.2)", color: "#5b7fba" };
    if (type === "jira")       return { bg: "rgba(74,158,107,0.15)", color: "#6dc28a" };
    return { bg: "var(--surface3)", color: "var(--text-dim)" };
  };

  return (
    <PanelCard id={cardId} icon="📎" title="Źródła" defaultOpen>
      {/* Tabs */}
      <div
        className="flex bg-buddy-base"
        style={{ gap: 2, marginBottom: 8, borderRadius: 4, padding: 2 }}
      >
        {(["files", "links"] as const).map((tab) => (
          <button
            key={tab}
            data-testid={`src-tab-${tab}`}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 transition-colors ${
              activeTab === tab
                ? "bg-buddy-surface2 border border-buddy-border text-buddy-text-muted"
                : "border border-transparent text-buddy-text-dim hover:text-buddy-text-muted"
            }`}
            style={{ padding: "4px 10px", borderRadius: 4, fontSize: 11, cursor: "pointer" }}
          >
            {tab === "files" ? "Pliki" : "Linki"}
          </button>
        ))}
      </div>

      {/* Files tab */}
      {activeTab === "files" && (
        <div>
          {newFiles.length > 0 && (
            <>
              <SectionLabel>Nowe</SectionLabel>
              <FileList files={newFiles} isNew onFileToggle={onFileToggle} />
            </>
          )}
          {usedFiles.length > 0 && (
            <>
              <SectionLabel>Poprzednio użyte</SectionLabel>
              <FileList files={usedFiles} isNew={false} onFileToggle={onFileToggle} />
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

      {/* Links tab */}
      {activeTab === "links" && (
        <div>
          {links.length > 0 ? (
            <div className="flex flex-col">
              {links.map((f) => {
                const style = linkBadgeStyle(f.source_type);
                const label = f.source_type === "confluence" ? "CONF"
                  : f.source_type === "jira" ? "JIRA" : "URL";
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
