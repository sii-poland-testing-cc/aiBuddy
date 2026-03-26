"use client";

import { useState } from "react";
import type { GlossaryTerm, ContextStatus } from "../lib/useContextBuilder";
import { PanelCard } from "./PanelCard";
import { SourcesCard } from "./SourcesCard";
import { TierButton } from "./TierButton";

type BuildMode = "append" | "rebuild";

export interface ContextModePanelProps {
  auditFiles?: never; // context mode builds its own file list from contextStatus
  onAddFiles?: () => void;
  onFileToggle?: (filePath: string, checked: boolean) => void;
  onDeleteContextDoc?: (filename: string) => void;
  onOpenMindMap?: () => void;
  glossary?: GlossaryTerm[];
  onTermClick?: (term: string) => void;
  contextStatus?: ContextStatus | null;
  buildMode?: BuildMode;
  onBuildModeChange?: (mode: BuildMode) => void;
  onBuild?: (mode: BuildMode) => void;
  pendingContextFiles?: string[];
  isBuildRunning?: boolean;
  jiraItems?: import("./SourcesCard").JiraItem[];
  onAddJiraIssue?: (key: string) => Promise<void>;
  onDeleteJiraIssue?: (id: string) => void;
  jiraConfigured?: boolean;
}

// ── Static mind map thumbnail SVG ─────────────────────────────────────────────

function MindMapThumbnail() {
  return (
    <svg viewBox="0 0 280 160" xmlns="http://www.w3.org/2000/svg" style={{ width: "100%", height: "auto", display: "block" }}>
      <defs>
        <marker id="arr-th" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill="#3a342c" />
        </marker>
      </defs>
      <g stroke="#3a342c" strokeWidth="1.2" fill="none" markerEnd="url(#arr-th)">
        <path d="M140,22 C140,38 85,50 85,62" />
        <path d="M140,22 C140,38 140,50 140,62" />
        <path d="M140,22 C140,38 195,50 195,62" />
      </g>
      <rect x="96" y="8" width="88" height="20" rx="5" fill="#c8902a" opacity="0.9" />
      <text x="140" y="22" textAnchor="middle" fill="#0f0d0a" fontSize="9" fontWeight="700" fontFamily="-apple-system,sans-serif">PayFlow System</text>
      <rect x="30" y="62" width="110" height="18" rx="4" fill="#2a2520" stroke="#4a9e6b" strokeWidth="1.2" />
      <text x="85" y="75" textAnchor="middle" fill="#4a9e6b" fontSize="8" fontFamily="-apple-system,sans-serif">Payment Gateway</text>
      <rect x="84" y="62" width="112" height="18" rx="4" fill="#2a2520" stroke="#5b7fba" strokeWidth="1.2" />
      <text x="140" y="75" textAnchor="middle" fill="#5b7fba" fontSize="8" fontFamily="-apple-system,sans-serif">User Auth</text>
      <rect x="140" y="62" width="110" height="18" rx="4" fill="#2a2520" stroke="#9b6bbf" strokeWidth="1.2" />
      <text x="195" y="75" textAnchor="middle" fill="#9b6bbf" fontSize="8" fontFamily="-apple-system,sans-serif">Order Mgmt</text>
    </svg>
  );
}

// ── ContextModePanel ───────────────────────────────────────────────────────────

export function ContextModePanel({
  onAddFiles,
  onFileToggle,
  onDeleteContextDoc,
  onOpenMindMap,
  glossary = [],
  onTermClick,
  contextStatus,
  buildMode = "append",
  onBuildModeChange,
  onBuild = () => {},
  pendingContextFiles = [],
  isBuildRunning = false,
  jiraItems = [],
  onAddJiraIssue,
  onDeleteJiraIssue,
  jiraConfigured = true,
}: ContextModePanelProps) {
  const [glossarySearch, setGlossarySearch] = useState("");
  const [localBuildMode, setLocalBuildMode] = useState<BuildMode>(buildMode);

  const filteredGlossary = glossary.filter(
    (t) =>
      !glossarySearch ||
      t.term.toLowerCase().includes(glossarySearch.toLowerCase()) ||
      t.definition.toLowerCase().includes(glossarySearch.toLowerCase())
  );

  const handleBuildModeChange = (m: BuildMode) => {
    setLocalBuildMode(m);
    onBuildModeChange?.(m);
  };

  // Build the file list for the sources card from pending + already-indexed docs
  const contextFiles = [
    ...pendingContextFiles.map((filename) => ({
      id: `pending-${filename}`,
      filename,
      file_path: filename,
      source_type: "file" as const,
      selected: true,
      isNew: true,
    })),
    ...(contextStatus?.context_files ?? [])
      .filter((f) => !pendingContextFiles.includes(f.name))
      .map((f) => ({
        id: f.name,
        filename: f.name,
        file_path: f.name,
        source_type: "file" as const,
        selected: true,
        isNew: false,
      })),
  ];

  return (
    <div data-testid="panel-mode-context" className="flex flex-col" style={{ gap: 6 }}>
      <SourcesCard
        cardId="sources-context"
        auditFiles={contextFiles}
        onAddFiles={onAddFiles}
        onFileToggle={onFileToggle}
        onDeleteFile={onDeleteContextDoc}
        jiraItems={jiraItems}
        onAddJira={onAddJiraIssue}
        onDeleteJira={onDeleteJiraIssue}
        jiraConfigured={jiraConfigured}
      />

      {/* Mind Map */}
      <PanelCard id="mindmap" icon="🗺" title="Mind Map" defaultOpen>
        <div
          className="relative cursor-pointer group"
          onClick={onOpenMindMap}
          data-testid="mindmap-thumbnail"
        >
          <MindMapThumbnail />
          <div
            className="absolute inset-0 flex flex-col items-center justify-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ background: "rgba(15,13,10,0.72)", borderRadius: 4 }}
          >
            <span className="font-semibold text-buddy-gold-light" style={{ fontSize: 12 }}>
              ⤢ Otwórz pełny widok
            </span>
            <span className="text-buddy-text-dim" style={{ fontSize: 10 }}>
              pan &amp; zoom · szukaj
            </span>
          </div>
        </div>
        <button
          data-testid="mindmap-fullscreen-btn"
          onClick={onOpenMindMap}
          className="mt-2 flex items-center gap-1.5 border border-buddy-border text-buddy-text-dim hover:text-buddy-gold-light hover:border-buddy-gold/40 transition-all"
          style={{ padding: "4px 10px", borderRadius: 4, fontSize: 11, background: "transparent", cursor: "pointer" }}
        >
          <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M1 5V1h4M9 1h4v4M13 9v4H9M5 13H1V9" />
          </svg>
          Pełny ekran
        </button>
      </PanelCard>

      {/* Glossary */}
      <PanelCard
        id="glossary"
        icon="📖"
        title="Glosariusz"
        badge={glossary.length || undefined}
      >
        <input
          type="text"
          placeholder="Szukaj terminów…"
          value={glossarySearch}
          onChange={(e) => setGlossarySearch(e.target.value)}
          data-testid="glossary-search"
          className="w-full bg-buddy-surface2 border border-buddy-border text-buddy-text placeholder:text-buddy-text-dim focus:outline-none focus:border-buddy-gold transition-colors"
          style={{ padding: "6px 10px", borderRadius: 4, fontSize: 12, marginBottom: 8 }}
        />
        <div style={{ maxHeight: 260, overflowY: "auto", scrollbarWidth: "thin" }}>
          {filteredGlossary.length > 0 ? (
            filteredGlossary.map((t) => (
              <div
                key={t.term}
                data-testid="glossary-term"
                onClick={() => onTermClick?.(t.term)}
                className="border border-buddy-border bg-buddy-base cursor-pointer hover:border-buddy-gold/50 hover:bg-buddy-elevated transition-all"
                style={{ padding: "8px 10px", borderRadius: 4, marginBottom: 4 }}
              >
                <div className="font-semibold text-buddy-text" style={{ fontSize: 12, marginBottom: 2 }}>
                  {t.term}
                </div>
                <div className="text-buddy-text-muted" style={{ fontSize: 11, lineHeight: 1.4 }}>
                  {t.definition}
                </div>
              </div>
            ))
          ) : (
            <p className="text-buddy-text-faint" style={{ fontSize: 11, textAlign: "center", padding: "8px 0" }}>
              {glossarySearch ? "Brak wyników" : "Brak terminów"}
            </p>
          )}
        </div>
      </PanelCard>

      {/* Context Status */}
      <PanelCard id="ctx-status" icon="⚙️" title="Status kontekstu">
        {contextStatus ? (
          <>
            {contextStatus.context_built_at && (
              <div style={{ fontSize: 10, color: "#4ade80", marginBottom: 6 }}>
                Kontekst zbudowany:{" "}
                {new Date(contextStatus.context_built_at).toLocaleString("pl-PL", {
                  day: "numeric", month: "short", year: "numeric",
                  hour: "2-digit", minute: "2-digit",
                })}
              </div>
            )}
            {contextStatus.stats && (
              <div className="flex" style={{ gap: 6, marginBottom: 8 }}>
                <span
                  className="font-mono"
                  style={{ padding: "2px 8px", borderRadius: 4, fontSize: 10, border: "1px solid", background: "rgba(200,144,42,0.1)", color: "#c8902a", borderColor: "rgba(200,144,42,0.2)" }}
                >
                  {contextStatus.stats.entity_count} encji
                </span>
                <span
                  className="font-mono bg-buddy-surface2 border border-buddy-border-light text-buddy-text-muted"
                  style={{ padding: "2px 8px", borderRadius: 4, fontSize: 10 }}
                >
                  {contextStatus.stats.term_count} terminów
                </span>
              </div>
            )}
            {contextStatus.context_files && contextStatus.context_files.length > 0 && (
              <>
                <div className="font-semibold uppercase text-buddy-text-faint" style={{ fontSize: 10, letterSpacing: "0.06em", marginBottom: 4 }}>
                  Zaindeksowane dokumenty:
                </div>
                {contextStatus.context_files.map((f) => (
                  <div
                    key={f.name}
                    className="font-mono text-buddy-text-muted overflow-hidden"
                    style={{ fontSize: 10, textOverflow: "ellipsis", whiteSpace: "nowrap", padding: "1px 0" }}
                  >
                    {f.name}
                    {f.indexed_at && (
                      <span className="text-buddy-text-faint" style={{ marginLeft: 6 }}>
                        {new Date(f.indexed_at).toLocaleString("pl-PL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                      </span>
                    )}
                  </div>
                ))}
              </>
            )}
            {contextStatus.jira_sources && contextStatus.jira_sources.length > 0 && (
              <>
                <div className="font-semibold uppercase text-buddy-text-faint" style={{ fontSize: 10, letterSpacing: "0.06em", marginBottom: 4, marginTop: 6 }}>
                  Jira:
                </div>
                {contextStatus.jira_sources.map((j) => (
                  <div
                    key={j.key}
                    className="font-mono text-buddy-text-muted overflow-hidden"
                    style={{ fontSize: 10, textOverflow: "ellipsis", whiteSpace: "nowrap", padding: "1px 0" }}
                  >
                    <span style={{ color: "#5b7fba" }}>{j.key}</span>
                    {j.indexed_at && (
                      <span className="text-buddy-text-faint" style={{ marginLeft: 6 }}>
                        {new Date(j.indexed_at).toLocaleString("pl-PL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                      </span>
                    )}
                  </div>
                ))}
              </>
            )}
            {!contextStatus.rag_ready && (
              <p className="text-buddy-text-dim" style={{ fontSize: 11 }}>Kontekst nie jest gotowy.</p>
            )}
          </>
        ) : (
          <p className="text-buddy-text-faint" style={{ fontSize: 11 }}>Brak danych o kontekście.</p>
        )}
      </PanelCard>

      {/* Build mode */}
      <PanelCard id="build-mode" icon="🔧" title="Tryb budowania">
        <div className="flex flex-col" style={{ gap: 4, marginBottom: 10 }}>
          <TierButton
            active={localBuildMode === "append"}
            onClick={() => handleBuildModeChange("append")}
          >
            Append — dołącz do istniejącego kontekstu
          </TierButton>
          <TierButton
            active={localBuildMode === "rebuild"}
            onClick={() => handleBuildModeChange("rebuild")}
          >
            Rebuild — przebuduj od zera
          </TierButton>
        </div>
        <button
          data-testid="build-btn"
          onClick={() => !isBuildRunning && onBuild(localBuildMode)}
          disabled={isBuildRunning}
          className="w-full font-semibold transition-opacity text-buddy-surface"
          style={{
            padding: 8, borderRadius: 5, border: "none", fontSize: 12,
            background: isBuildRunning
              ? "linear-gradient(135deg, #7a5618, #9a7028)"
              : "linear-gradient(135deg, #c8902a, #e0aa42)",
            cursor: isBuildRunning ? "not-allowed" : "pointer",
            opacity: isBuildRunning ? 0.65 : 1,
          }}
        >
          {isBuildRunning ? "⏳ Budowanie w toku…" : "▶ Uruchom budowanie"}
        </button>
      </PanelCard>
    </div>
  );
}
