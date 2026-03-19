"use client";

import { useState } from "react";
import { GlossaryTerm, ContextStatus } from "../lib/useContextBuilder";
import { HeatmapRow } from "../lib/useHeatmap";

// ── Types ─────────────────────────────────────────────────────────────────────

type Mode = "context" | "requirements" | "audit";
type BuildMode = "append" | "rebuild";
type Tier = "audit" | "optimize" | "regenerate" | "rag_chat";

export interface PanelFile {
  id: string;
  filename: string;
  file_path: string;
  source_type: "file" | "url" | "jira" | "confluence";
  selected: boolean;
  isNew: boolean; // last_used_in_audit_id === null
}

export interface AuditSnapshot {
  id: string;
  created_at: string;
  summary: { coverage_pct: number };
  diff: { coverage_delta: number | null } | null;
}

interface UtilityPanelProps {
  open: boolean;
  activeMode: Mode;
  projectId: string;
  // Sources
  projectFiles?: PanelFile[];
  onAddFiles?: () => void;
  onFileToggle?: (filePath: string, checked: boolean) => void;
  // Mind Map
  onOpenMindMap?: () => void;
  // Glossary
  glossary?: GlossaryTerm[];
  onTermClick?: (term: string) => void;
  // Context Status
  contextStatus?: ContextStatus | null;
  // Build mode
  buildMode?: BuildMode;
  onBuildModeChange?: (mode: BuildMode) => void;
  onBuild?: (mode: BuildMode) => void;
  // Heatmap
  heatmapData?: HeatmapRow[];
  // Mapping
  lastMappingDate?: string | null;
  onRunMapping?: () => void;
  // Audit snapshots
  snapshots?: AuditSnapshot[];
  latestSnapshotId?: string | null;
  // Tier
  tier?: Tier;
  onTierChange?: (tier: Tier) => void;
}

// ── Helper: file extension icon colors (matching v3) ──────────────────────────

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

// ── PanelCard ─────────────────────────────────────────────────────────────────

function PanelCard({
  id,
  icon,
  title,
  badge,
  defaultOpen = false,
  children,
}: {
  id: string;
  icon: string;
  title: string;
  badge?: string | number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      data-testid={`card-${id}`}
      className="border border-buddy-border bg-buddy-base overflow-hidden"
      style={{ borderRadius: 6 }}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => e.key === "Enter" && setOpen((o) => !o)}
        className="flex items-center gap-1.5 cursor-pointer select-none hover:bg-buddy-elevated transition-colors"
        style={{ padding: "9px 12px" }}
      >
        <span style={{ fontSize: 13 }}>{icon}</span>
        <span
          className="flex-1 font-semibold uppercase tracking-widest text-buddy-text-muted"
          style={{ fontSize: 11, letterSpacing: "0.05em" }}
        >
          {title}
        </span>
        {badge !== undefined && (
          <span
            className="bg-buddy-surface2 border border-buddy-border text-buddy-text-dim font-mono"
            style={{ padding: "1px 6px", borderRadius: 4, fontSize: 10 }}
          >
            {badge}
          </span>
        )}
        <span
          className="text-buddy-text-dim"
          style={{
            fontSize: 10,
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s",
          }}
        >
          ▲
        </span>
      </div>
      {open && (
        <div className="border-t border-buddy-border" style={{ padding: 12 }}>
          {children}
        </div>
      )}
    </div>
  );
}

// ── SourcesCard (shared across all modes) ─────────────────────────────────────

function SourcesCard({
  cardId,
  projectFiles = [],
  onAddFiles,
  onFileToggle,
}: {
  cardId: string;
  projectFiles: PanelFile[];
  onAddFiles?: () => void;
  onFileToggle?: (filePath: string, checked: boolean) => void;
}) {
  const [activeTab, setActiveTab] = useState<"files" | "links">("files");

  const newFiles  = projectFiles.filter((f) => f.source_type === "file" && f.isNew);
  const usedFiles = projectFiles.filter((f) => f.source_type === "file" && !f.isNew);
  const links     = projectFiles.filter((f) => f.source_type !== "file");

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
          {projectFiles.filter((f) => f.source_type === "file").length === 0 && (
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

// ── TierButton ────────────────────────────────────────────────────────────────

function TierButton({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`w-full text-left transition-all ${
        active
          ? "bg-buddy-gold/15 border-buddy-gold/50 text-buddy-gold-light font-medium"
          : disabled
          ? "border-buddy-border text-buddy-text-dim opacity-40 cursor-not-allowed"
          : "border-buddy-border text-buddy-text-muted hover:border-buddy-border-dark hover:text-buddy-text"
      }`}
      style={{ padding: "8px 12px", borderRadius: 5, fontSize: 12, border: "1px solid", background: active ? undefined : "transparent", cursor: disabled ? "not-allowed" : "pointer" }}
    >
      {children}
    </button>
  );
}

// ── Heatmap color emoji ───────────────────────────────────────────────────────

function heatmapEmoji(color: HeatmapRow["color"]) {
  return { green: "🟢", yellow: "🟡", orange: "🟠", red: "🔴" }[color];
}

// ── Coverage badge ────────────────────────────────────────────────────────────

function CovBadge({ pct }: { pct: number }) {
  const cls = pct >= 80 ? "rgba(74,158,107,0.2) #4a9e6b"
    : pct >= 50 ? "rgba(200,144,42,0.2) #c8902a"
    : "rgba(192,80,74,0.2) #e08080";
  const [bg, color] = cls.split(" ");
  return (
    <span
      className="font-mono font-bold"
      style={{ padding: "1px 6px", borderRadius: 3, fontSize: 10, background: bg, color }}
    >
      {Math.round(pct)}%
    </span>
  );
}

// ── DiffBadge ─────────────────────────────────────────────────────────────────

function DiffBadge({ delta }: { delta: number | null }) {
  if (delta === null) return <span className="text-buddy-text-dim" style={{ fontSize: 10 }}>→ first</span>;
  if (delta > 0) return <span style={{ fontSize: 10, padding: "1px 5px", borderRadius: 3, background: "rgba(74,158,107,0.2)", color: "#4a9e6b" }}>▲ +{delta}%</span>;
  if (delta < 0) return <span style={{ fontSize: 10, padding: "1px 5px", borderRadius: 3, background: "rgba(192,80,74,0.2)", color: "#e08080" }}>▼ {delta}%</span>;
  return <span className="text-buddy-text-dim" style={{ fontSize: 10 }}>→</span>;
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

// ── Main component ─────────────────────────────────────────────────────────────

export default function UtilityPanel({
  open,
  activeMode,
  projectFiles = [],
  onAddFiles = () => console.log("onAddFiles"),
  onFileToggle,
  onOpenMindMap = () => console.log("onOpenMindMap"),
  glossary = [],
  onTermClick,
  contextStatus,
  buildMode = "append",
  onBuildModeChange,
  onBuild = (m) => console.log("onBuild", m),
  heatmapData = [],
  lastMappingDate,
  onRunMapping = () => console.log("onRunMapping"),
  snapshots = [],
  latestSnapshotId,
  tier = "audit",
  onTierChange,
}: UtilityPanelProps) {
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

  return (
    <aside
      data-testid="utility-panel"
      className="flex-shrink-0 bg-buddy-surface border-l border-buddy-border flex flex-col overflow-y-auto"
      style={{
        width: open ? 300 : 0,
        padding: open ? 10 : 0,
        gap: 6,
        overflowX: "hidden",
        transition: "width 0.25s cubic-bezier(0.4,0,0.2,1), padding 0.25s",
        scrollbarWidth: "thin",
      }}
    >
      {open && (
        <>
          {/* ── CONTEXT mode ── */}
          {activeMode === "context" && (
            <div data-testid="panel-mode-context" className="flex flex-col" style={{ gap: 6 }}>
              <SourcesCard
                cardId="sources-context"
                projectFiles={projectFiles}
                onAddFiles={onAddFiles}
                onFileToggle={onFileToggle}
              />

              {/* Mind Map */}
              <PanelCard id="mindmap" icon="🗺" title="Mind Map" defaultOpen>
                <div
                  className="relative cursor-pointer group"
                  onClick={onOpenMindMap}
                  data-testid="mindmap-thumbnail"
                >
                  <MindMapThumbnail />
                  {/* Hover overlay */}
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
                            key={f}
                            className="font-mono text-buddy-text-muted overflow-hidden"
                            style={{ fontSize: 10, textOverflow: "ellipsis", whiteSpace: "nowrap", padding: "1px 0" }}
                          >
                            {f}
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
                  onClick={() => onBuild(localBuildMode)}
                  className="w-full font-semibold transition-opacity hover:opacity-[0.88] text-buddy-surface"
                  style={{
                    padding: 8, borderRadius: 5, border: "none", cursor: "pointer", fontSize: 12,
                    background: "linear-gradient(135deg, #c8902a, #e0aa42)",
                  }}
                >
                  ▶ Uruchom budowanie
                </button>
              </PanelCard>
            </div>
          )}

          {/* ── REQUIREMENTS mode ── */}
          {activeMode === "requirements" && (
            <div data-testid="panel-mode-requirements" className="flex flex-col" style={{ gap: 6 }}>
              <SourcesCard
                cardId="sources-requirements"
                projectFiles={projectFiles}
                onAddFiles={onAddFiles}
                onFileToggle={onFileToggle}
              />

              {/* Heatmap */}
              <PanelCard id="heatmap" icon="🗂" title="Heatmap pokrycia" defaultOpen>
                {heatmapData.length > 0 ? (
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                    <thead>
                      <tr>
                        <th className="text-buddy-text-faint font-medium border-b border-buddy-border" style={{ padding: "5px 8px", textAlign: "left" }}>Moduł</th>
                        <th className="text-buddy-text-faint font-medium border-b border-buddy-border" style={{ padding: "5px 8px", textAlign: "right" }}>Wym.</th>
                        <th className="text-buddy-text-faint font-medium border-b border-buddy-border" style={{ padding: "5px 8px", textAlign: "right" }}>Pokr.</th>
                        <th className="text-buddy-text-faint font-medium border-b border-buddy-border" style={{ padding: "5px 8px", textAlign: "right" }}>Śr.</th>
                        <th className="text-buddy-text-faint font-medium border-b border-buddy-border" style={{ padding: "5px 8px", textAlign: "center" }}>St.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {heatmapData.map((row) => (
                        <tr key={row.module} className="hover:bg-white/[0.02] transition-colors">
                          <td className="text-buddy-text font-medium font-mono border-b border-buddy-border" style={{ padding: "6px 8px" }}>{row.module}</td>
                          <td className="text-buddy-text-muted border-b border-buddy-border" style={{ padding: "6px 8px", textAlign: "right" }}>{row.total_requirements}</td>
                          <td className="text-buddy-text-muted border-b border-buddy-border" style={{ padding: "6px 8px", textAlign: "right" }}>{row.covered}</td>
                          <td className="font-mono text-buddy-text-muted border-b border-buddy-border" style={{ padding: "6px 8px", textAlign: "right" }}>{row.avg_score.toFixed(1)}</td>
                          <td className="border-b border-buddy-border" style={{ padding: "6px 8px", textAlign: "center" }}>{heatmapEmoji(row.color)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="text-buddy-text-faint" style={{ fontSize: 11, textAlign: "center", padding: "8px 0" }}>
                    Brak danych heatmapy. Uruchom mapowanie.
                  </p>
                )}
              </PanelCard>

              {/* Mapping */}
              <PanelCard id="mapping" icon="🔗" title="Mapowanie" defaultOpen>
                {lastMappingDate && (
                  <div className="text-buddy-text-dim" style={{ fontSize: 11, marginBottom: 8 }}>
                    Ostatnie mapowanie:{" "}
                    {new Date(lastMappingDate).toLocaleDateString("pl-PL", { day: "numeric", month: "short", year: "numeric" })}
                  </div>
                )}
                <button
                  data-testid="run-mapping-btn"
                  onClick={onRunMapping}
                  className="w-full border border-buddy-border text-buddy-text-muted hover:border-buddy-border-dark hover:text-buddy-text transition-all"
                  style={{ padding: "8px 12px", borderRadius: 5, fontSize: 11, background: "transparent", cursor: "pointer", textAlign: "center" }}
                >
                  Uruchom mapowanie →
                </button>
              </PanelCard>
            </div>
          )}

          {/* ── AUDIT mode ── */}
          {activeMode === "audit" && (
            <div data-testid="panel-mode-audit" className="flex flex-col" style={{ gap: 6 }}>
              <SourcesCard
                cardId="sources-audit"
                projectFiles={projectFiles}
                onAddFiles={onAddFiles}
                onFileToggle={onFileToggle}
              />

              {/* Audit History */}
              <PanelCard
                id="history"
                icon="📋"
                title="Historia audytów"
                badge={snapshots.length || undefined}
              >
                {snapshots.length > 0 ? (
                  <div className="flex flex-col" style={{ gap: 3 }}>
                    {snapshots.map((snap) => {
                      const isLatest = snap.id === latestSnapshotId;
                      const pct = snap.summary?.coverage_pct ?? 0;
                      const delta = snap.diff?.coverage_delta ?? null;
                      const date = new Date(snap.created_at).toLocaleDateString("pl-PL", {
                        year: "numeric", month: "2-digit", day: "2-digit",
                      }).replace(/\./g, "-");
                      return (
                        <div
                          key={snap.id}
                          data-testid="snapshot-row"
                          className="flex items-center gap-2 border rounded-[4px] transition-colors hover:bg-buddy-elevated"
                          style={{
                            padding: "5px 8px",
                            borderColor: isLatest ? "rgba(200,144,42,0.35)" : "var(--border)",
                            background: isLatest ? "rgba(200,144,42,0.08)" : "transparent",
                          }}
                        >
                          <span className="font-mono text-buddy-text-dim" style={{ fontSize: 10, minWidth: 70 }}>
                            {date}
                          </span>
                          <CovBadge pct={pct} />
                          <DiffBadge delta={delta} />
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-buddy-text-faint" style={{ fontSize: 11, textAlign: "center", padding: "8px 0" }}>
                    Brak historii audytów.
                  </p>
                )}
              </PanelCard>

              {/* Tier selector */}
              <PanelCard id="tier" icon="⚡" title="Tryb analizy">
                <div className="flex flex-col" style={{ gap: 4 }}>
                  <TierButton
                    active={tier === "audit"}
                    onClick={() => onTierChange?.("audit")}
                  >
                    Audyt
                  </TierButton>
                  <TierButton
                    active={tier === "optimize"}
                    onClick={() => onTierChange?.("optimize")}
                  >
                    Optymalizacja
                  </TierButton>
                  <TierButton active={false} disabled>
                    Regeneracja (wkrótce)
                  </TierButton>
                </div>
              </PanelCard>
            </div>
          )}
        </>
      )}
    </aside>
  );
}
