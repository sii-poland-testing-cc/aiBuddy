"use client";

import { useState } from "react";
import type { MappingProgress } from "../lib/useMapping";
import type { AuditData } from "../lib/useAIBuddyChat";
import type { PanelFile, AuditSnapshot } from "../lib/types";
import { PanelCard } from "./PanelCard";
import { SourcesCard } from "./SourcesCard";
import { TierButton } from "./TierButton";
import { AuditResultCard } from "./AuditResultCard";

type Tier = "audit" | "optimize" | "regenerate" | "rag_chat";

export interface AuditModePanelProps {
  auditFiles?: PanelFile[];
  onAddFiles?: () => void;
  onFileToggle?: (filePath: string, checked: boolean) => void;
  lastMappingDate?: string | null;
  isMappingRunning?: boolean;
  mappingProgress?: MappingProgress | null;
  onRunMapping?: () => void;
  snapshots?: AuditSnapshot[];
  latestSnapshotId?: string | null;
  onAuditPipeline?: (message: string) => void;
  tier?: Tier;
  onTierChange?: (tier: Tier) => void;
}

// ── CovBadge ──────────────────────────────────────────────────────────────────

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

// ── SnapshotDiffBadge ─────────────────────────────────────────────────────────

function SnapshotDiffBadge({ delta }: { delta: number | null }) {
  if (delta === null) return <span className="text-buddy-text-dim" style={{ fontSize: 10 }}>→ first</span>;
  if (delta > 0) return <span style={{ fontSize: 10, padding: "1px 5px", borderRadius: 3, background: "rgba(74,158,107,0.2)", color: "#4a9e6b" }}>▲ +{delta}%</span>;
  if (delta < 0) return <span style={{ fontSize: 10, padding: "1px 5px", borderRadius: 3, background: "rgba(192,80,74,0.2)", color: "#e08080" }}>▼ {delta}%</span>;
  return <span className="text-buddy-text-dim" style={{ fontSize: 10 }}>→</span>;
}

// ── AuditModePanel ────────────────────────────────────────────────────────────

export function AuditModePanel({
  auditFiles = [],
  onAddFiles,
  onFileToggle,
  lastMappingDate,
  isMappingRunning = false,
  mappingProgress,
  onRunMapping = () => {},
  snapshots = [],
  latestSnapshotId,
  onAuditPipeline,
  tier = "audit",
  onTierChange,
}: AuditModePanelProps) {
  const [openSnap, setOpenSnap] = useState<AuditSnapshot | null>(null);

  return (
    <>
      <div data-testid="panel-mode-audit" className="flex flex-col" style={{ gap: 6 }}>
        <button
          data-testid="run-audit-pipeline-btn"
          onClick={() => onAuditPipeline?.("Uruchom audyt")}
          disabled={!onAuditPipeline}
          className="w-full font-semibold text-buddy-surface disabled:opacity-40 disabled:cursor-not-allowed transition-opacity hover:opacity-[0.88]"
          style={{ padding: "9px 12px", borderRadius: 6, border: "none", cursor: "pointer", fontSize: 12, background: "linear-gradient(135deg, #c8902a, #e0aa42)" }}
        >
          ▶ Uruchom audyt
        </button>

        <SourcesCard
          cardId="sources-audit"
          auditFiles={auditFiles}
          onAddFiles={onAddFiles}
          onFileToggle={onFileToggle}
        />

        {/* Mapping */}
        <PanelCard id="mapping" icon="🔗" title="Mapowanie" defaultOpen>
          {lastMappingDate && !isMappingRunning && (
            <div className="text-buddy-text-dim" style={{ fontSize: 11, marginBottom: 8 }}>
              Ostatnie mapowanie:{" "}
              {new Date(lastMappingDate).toLocaleDateString("pl-PL", { day: "numeric", month: "short", year: "numeric" })}
            </div>
          )}
          {isMappingRunning && mappingProgress && (
            <div style={{ marginBottom: 8 }}>
              <div className="text-buddy-text-muted" style={{ fontSize: 11, marginBottom: 4 }}>
                {mappingProgress.message}
              </div>
              <div className="bg-buddy-surface2 rounded-full overflow-hidden" style={{ height: 4 }}>
                <div
                  className="h-full transition-all duration-300"
                  style={{ width: `${Math.round(mappingProgress.progress * 100)}%`, background: "#c8902a" }}
                />
              </div>
            </div>
          )}
          <button
            data-testid="run-mapping-btn"
            onClick={onRunMapping}
            disabled={isMappingRunning}
            className="w-full border border-buddy-border text-buddy-text-muted hover:border-buddy-border-dark hover:text-buddy-text transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ padding: "8px 12px", borderRadius: 5, fontSize: 11, background: "transparent", cursor: isMappingRunning ? "not-allowed" : "pointer", textAlign: "center" }}
          >
            {isMappingRunning ? "Mapowanie w toku…" : "Uruchom mapowanie →"}
          </button>
        </PanelCard>

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
                    <SnapshotDiffBadge delta={delta} />
                    <button
                      data-testid="snapshot-open-btn"
                      onClick={() => setOpenSnap(snap)}
                      title="Otwórz wyniki audytu"
                      style={{
                        marginLeft: "auto", background: "none", border: "none",
                        cursor: "pointer", fontSize: 11, color: "#6a5f50",
                        padding: "0 2px", lineHeight: 1, transition: "color 0.15s",
                      }}
                      className="hover:!text-buddy-gold"
                    >
                      ↗
                    </button>
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
            <TierButton active={tier === "audit"} onClick={() => onTierChange?.("audit")}>
              Audyt
            </TierButton>
            <TierButton active={tier === "optimize"} onClick={() => onTierChange?.("optimize")}>
              Optymalizacja
            </TierButton>
            <TierButton active={false} disabled>
              Regeneracja (wkrótce)
            </TierButton>
          </div>
        </PanelCard>
      </div>

      {/* Snapshot detail modal */}
      {openSnap && (() => {
        const snap = openSnap;
        const auditData: AuditData = {
          summary: {
            coverage_pct: snap.summary.coverage_pct,
            duplicates_found: snap.summary.duplicates_found ?? 0,
            untagged_cases: snap.summary.untagged_cases ?? 0,
            requirements_total: snap.summary.requirements_total ?? 0,
            requirements_covered: snap.summary.requirements_covered ?? 0,
          },
          uncovered: snap.requirements_uncovered ?? [],
          recommendations: snap.recommendations ?? [],
          duplicates: [],
          diff: snap.diff !== null
            ? { coverage_delta: snap.diff?.coverage_delta ?? 0, new_covered: snap.diff?.new_covered ?? [], newly_uncovered: snap.diff?.newly_uncovered ?? [] }
            : null,
        };
        const dateStr = new Date(snap.created_at).toLocaleString("pl-PL", {
          year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
        });
        return (
          <div
            data-testid="audit-modal"
            onClick={(e) => { if (e.target === e.currentTarget) setOpenSnap(null); }}
            style={{
              position: "fixed", inset: 0, zIndex: 2000,
              background: "rgba(0,0,0,0.65)", backdropFilter: "blur(2px)",
              display: "flex", alignItems: "center", justifyContent: "center",
              padding: 24,
            }}
          >
            <div style={{
              width: "100%", maxWidth: 640, maxHeight: "85vh",
              overflowY: "auto", borderRadius: 10,
              background: "#1a1612", border: "1px solid #3a342c",
              boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
            }}>
              <div style={{ padding: "12px 16px 0", display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid #2a2520", marginBottom: 0, paddingBottom: 10 }}>
                <span style={{ fontSize: 11, color: "#6a5f50", fontFamily: "monospace" }}>{dateStr}</span>
                {snap.files_used && snap.files_used.length > 0 && (
                  <span style={{ fontSize: 10, color: "#4a3f32", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    — {snap.files_used.map((p) => p.split("/").pop()).join(", ")}
                  </span>
                )}
              </div>
              <div style={{ padding: "0 16px 16px" }}>
                <AuditResultCard data={auditData} onClose={() => setOpenSnap(null)} />
              </div>
            </div>
          </div>
        );
      })()}
    </>
  );
}
