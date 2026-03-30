"use client";

import { GlossaryTerm, ContextStatus } from "../lib/useContextBuilder";
import { HeatmapRow } from "../lib/useHeatmap";
import { MappingProgress } from "../lib/useMapping";
import { ContextModePanel } from "./ContextModePanel";
import { RequirementsModePanel } from "./RequirementsModePanel";
import { AuditModePanel } from "./AuditModePanel";

// ── Types ─────────────────────────────────────────────────────────────────────

import type { PanelFile, AuditSnapshot } from "../lib/types";

type Mode = "context" | "requirements" | "audit";
type BuildMode = "append" | "rebuild";
type Tier = "audit" | "optimize" | "regenerate" | "rag_chat";

interface UtilityPanelProps {
  open: boolean;
  activeMode: Mode;
  projectId: string;
  // Sources
  auditFiles?: PanelFile[];
  onAddFiles?: () => void;
  onFileToggle?: (filePath: string, checked: boolean) => void;
  onDeleteFile?: (id: string) => void;
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
  isBuildRunning?: boolean;
  // Pending context files (selected but not yet built)
  pendingContextFiles?: string[];
  // Heatmap
  heatmapData?: HeatmapRow[];
  // Mapping
  lastMappingDate?: string | null;
  isMappingRunning?: boolean;
  mappingProgress?: MappingProgress | null;
  onRunMapping?: () => void;
  // Audit snapshots
  snapshots?: AuditSnapshot[];
  latestSnapshotId?: string | null;
  // Audit pipeline
  onAuditPipeline?: (message: string) => void;
  // Tier
  tier?: Tier;
  onTierChange?: (tier: Tier) => void;
  // Jira
  jiraItems?: import("./SourcesCard").JiraItem[];
  onAddJiraIssue?: (key: string) => Promise<void>;
  onDeleteJiraIssue?: (id: string) => void;
  projectSettings?: { jira_url?: string; jira_api_key?: string };
}

// ── UtilityPanel (thin shell) ──────────────────────────────────────────────────

export default function UtilityPanel({
  open,
  activeMode,
  projectId,
  auditFiles = [],
  onAddFiles,
  onFileToggle,
  onDeleteFile,
  onOpenMindMap,
  glossary = [],
  onTermClick,
  contextStatus,
  buildMode = "append",
  onBuildModeChange,
  onBuild,
  isBuildRunning = false,
  pendingContextFiles = [],
  heatmapData = [],
  lastMappingDate,
  isMappingRunning = false,
  mappingProgress,
  onRunMapping,
  onAuditPipeline,
  snapshots = [],
  latestSnapshotId,
  tier = "audit",
  onTierChange,
  jiraItems = [],
  onAddJiraIssue,
  onDeleteJiraIssue,
  projectSettings,
}: UtilityPanelProps) {
  const jiraConfigured = !!(projectSettings?.jira_url && projectSettings?.jira_api_key);
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
          {activeMode === "context" && (
            <ContextModePanel
              onAddFiles={onAddFiles}
              onFileToggle={onFileToggle}
              onDeleteContextDoc={onDeleteFile}
              onOpenMindMap={onOpenMindMap}
              glossary={glossary}
              onTermClick={onTermClick}
              contextStatus={contextStatus}
              buildMode={buildMode}
              onBuildModeChange={onBuildModeChange}
              onBuild={onBuild}
              isBuildRunning={isBuildRunning}
              pendingContextFiles={pendingContextFiles}
              jiraItems={jiraItems}
              onAddJiraIssue={onAddJiraIssue}
              onDeleteJiraIssue={onDeleteJiraIssue}
              jiraConfigured={jiraConfigured}
            />
          )}

          {activeMode === "requirements" && (
            <RequirementsModePanel
              auditFiles={auditFiles}
              onAddFiles={onAddFiles}
              onFileToggle={onFileToggle}
              onDeleteFile={onDeleteFile}
              heatmapData={heatmapData}
              onAddJiraIssue={onAddJiraIssue}
              onDeleteJiraIssue={onDeleteJiraIssue}
              jiraConfigured={jiraConfigured}
            />
          )}

          {activeMode === "audit" && (
            <AuditModePanel
              auditFiles={auditFiles}
              onAddFiles={onAddFiles}
              onFileToggle={onFileToggle}
              onDeleteFile={onDeleteFile}
              lastMappingDate={lastMappingDate}
              isMappingRunning={isMappingRunning}
              mappingProgress={mappingProgress}
              onRunMapping={onRunMapping}
              snapshots={snapshots}
              latestSnapshotId={latestSnapshotId}
              onAuditPipeline={onAuditPipeline}
              tier={tier}
              onTierChange={onTierChange}
              onAddJiraIssue={onAddJiraIssue}
              onDeleteJiraIssue={onDeleteJiraIssue}
              jiraConfigured={jiraConfigured}
            />
          )}
        </>
      )}
    </aside>
  );
}
