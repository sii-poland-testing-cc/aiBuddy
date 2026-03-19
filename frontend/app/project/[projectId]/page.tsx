"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useSearchParams } from "next/navigation";
import TopBar from "@/components/TopBar";
import MessageList from "@/components/MessageList";
import ModeInputBox from "@/components/ModeInputBox";
import UtilityPanel, { PanelFile, AuditSnapshot } from "@/components/UtilityPanel";
import MindMapModal, { layoutModalNodes } from "@/components/MindMapModal";
import { useAIBuddyChat } from "@/lib/useAIBuddyChat";
import { useContextBuilder } from "@/lib/useContextBuilder";
import type { GlossaryTerm as ContextGlossaryTerm } from "@/lib/useContextBuilder";
import { useProjectFiles } from "@/lib/useProjectFiles";
import { useHeatmap } from "@/lib/useHeatmap";
import { useRequirements } from "@/lib/useRequirements";
import RequirementsView from "@/components/RequirementsView";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Mode = "context" | "requirements" | "audit";
type Tier = "audit" | "optimize" | "regenerate" | "rag_chat";
type BuildMode = "append" | "rebuild";

interface AttachedFile {
  name: string;
}

// ── Snapshot fetching ──────────────────────────────────────────────────────────

function useSnapshots(projectId: string, latestSnapshotId?: string) {
  const [snapshots, setSnapshots] = useState<AuditSnapshot[]>([]);

  const fetchSnapshots = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/snapshots/${projectId}`);
      if (res.ok) {
        const data = await res.json();
        setSnapshots(
          data.map((s: any) => ({
            id: s.id,
            created_at: s.created_at,
            summary: typeof s.summary === "string" ? JSON.parse(s.summary) : s.summary,
            diff: typeof s.diff === "string" ? JSON.parse(s.diff) : s.diff,
          }))
        );
      }
    } catch {
      /* backend offline */
    }
  }, [projectId]);

  useEffect(() => { fetchSnapshots(); }, [fetchSnapshots]);
  // Re-fetch when a new audit completes
  useEffect(() => { if (latestSnapshotId) fetchSnapshots(); }, [latestSnapshotId, fetchSnapshots]);

  return snapshots;
}

// ── Panel file fetching ────────────────────────────────────────────────────────

function usePanelFiles(projectId: string, refreshKey: number): [PanelFile[], (fp: string, checked: boolean) => void] {
  const [panelFiles, setPanelFiles] = useState<PanelFile[]>([]);

  useEffect(() => {
    fetch(`${API_BASE}/api/files/${projectId}/audit-selection`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data: any[]) => {
        setPanelFiles(
          data.map((f) => ({
            id: f.id,
            filename: f.filename,
            file_path: f.file_path,
            source_type: f.source_type as PanelFile["source_type"],
            selected: f.selected,
            isNew: f.last_used_in_audit_id === null,
          }))
        );
      })
      .catch(() => {});
  }, [projectId, refreshKey]);

  const handleFileToggle = useCallback((filePath: string, checked: boolean) => {
    setPanelFiles((prev) =>
      prev.map((f) => (f.file_path === filePath ? { ...f, selected: checked } : f))
    );
  }, []);

  return [panelFiles, handleFileToggle];
}

// ── Unified Project Page ───────────────────────────────────────────────────────

export default function ProjectPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = decodeURIComponent(params.projectId);
  const searchParams = useSearchParams();

  // ── Core state ──────────────────────────────────────────────────────────────
  const initialMode = (() => {
    const m = searchParams.get("mode");
    if (m === "context" || m === "requirements" || m === "audit") return m;
    return "audit";
  })();
  const [activeMode, setActiveMode] = useState<Mode>(initialMode);
  const [panelOpen, setPanelOpen] = useState(true);
  const [mmModalOpen, setMmModalOpen] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [tier, setTier] = useState<Tier>(initialMode === "context" ? "rag_chat" : "audit");
  const [buildMode, setBuildMode] = useState<BuildMode>("append");
  const [refreshKey, setRefreshKey] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Hooks ───────────────────────────────────────────────────────────────────
  const {
    messages, progress, isLoading, error: chatError,
    latestSnapshotId, send, stop, clearError,
  } = useAIBuddyChat({ projectId, tier });

  const {
    result: ctxResult, status: contextStatus,
    isBuilding, buildContext, fetchStatus,
  } = useContextBuilder(projectId);

  const { files: rawFiles, uploading, uploadFiles } = useProjectFiles(projectId);
  const { heatmap, retry: retryHeatmap } = useHeatmap(projectId);
  const {
    requirements, stats: reqStats, loading: reqLoading, error: reqError,
    isExtracting, extractionProgress,
    extractRequirements, patchRequirement, refresh: refreshRequirements,
  } = useRequirements(projectId);

  const snapshots = useSnapshots(projectId, latestSnapshotId);
  const [panelFiles, handleFileToggle] = usePanelFiles(projectId, refreshKey);

  // Refresh panel files + snapshots after audit completes
  useEffect(() => {
    if (latestSnapshotId) setRefreshKey((k) => k + 1);
  }, [latestSnapshotId]);

  // Refresh context status on mount
  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  // ── Derived data ────────────────────────────────────────────────────────────
  const mindMapNodes = ctxResult?.mind_map?.nodes ?? [];
  const mindMapEdges = ctxResult?.mind_map?.edges ?? [];
  // Pre-computed layout for fullscreen modal (dagre x/y + depth)
  const modalNodes = layoutModalNodes(mindMapNodes, mindMapEdges);
  const ctxGlossary: ContextGlossaryTerm[] = ctxResult?.glossary ?? [];
  const ragReady = contextStatus?.rag_ready ?? false;

  // ── Handlers ────────────────────────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    if (!inputValue.trim() && attachedFiles.length === 0) return;
    const selectedPaths = panelFiles
      .filter((f) => f.selected)
      .map((f) => f.file_path);
    const attachedPaths = attachedFiles.map((f) => f.name); // placeholder paths
    await send(inputValue, [...selectedPaths, ...attachedPaths]);
    setInputValue("");
    setAttachedFiles([]);
  }, [inputValue, attachedFiles, panelFiles, send]);

  const handleTermClick = useCallback((term: ContextGlossaryTerm) => {
    setInputValue(`wyjaśnij termin: ${term.term}`);
  }, []);

  const handleUtilityTermClick = useCallback((termName: string) => {
    send(`wyjaśnij termin: ${termName}`, []);
  }, [send]);

  const handleAttachFiles = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInputChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      if (!files.length) return;
      const paths = await uploadFiles(files);
      setAttachedFiles((prev) => [
        ...prev,
        ...files.map((f) => ({ name: f.name })),
      ]);
      setRefreshKey((k) => k + 1);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [uploadFiles]
  );

  const handleBuild = useCallback(
    async (mode: BuildMode) => {
      // Trigger a file picker for context documents
      const input = document.createElement("input");
      input.type = "file";
      input.multiple = true;
      input.accept = ".docx,.pdf";
      input.onchange = async () => {
        const files = Array.from(input.files ?? []);
        if (files.length) await buildContext(files, mode);
      };
      input.click();
    },
    [buildContext]
  );

  const handleExtract = useCallback(async () => {
    await extractRequirements();
    retryHeatmap();
  }, [extractRequirements, retryHeatmap]);

  const handleMarkReviewed = useCallback((id: string) => {
    patchRequirement(id, { human_reviewed: true, needs_review: false });
  }, [patchRequirement]);

  const handleModeChange = useCallback((mode: Mode) => {
    setActiveMode(mode);
    setTier(mode === "context" ? "rag_chat" : "audit");
  }, []);

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col bg-buddy-base" style={{ height: "100vh" }}>

      {/* Hidden file input for test-file attachment */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".xlsx,.csv,.json,.pdf,.feature,.txt,.md"
        className="hidden"
        onChange={handleFileInputChange}
      />

      {/* ── TopBar ─────────────────────────────────────────────────────────── */}
      <TopBar
        projectId={projectId}
        onTogglePanel={() => setPanelOpen((o) => !o)}
        panelOpen={panelOpen}
        ragReady={ragReady}
      />

      {/* ── Main: chat + artifact + utility ────────────────────────────────── */}
      <div
        className="flex overflow-hidden"
        style={{ flex: 1, marginTop: 48 }}
      >

        {/* ── Chat column ──────────────────────────────────────────────────── */}
        <div className="flex flex-col flex-1 min-w-0 overflow-hidden">

          {/* Extraction progress bar (requirements mode) */}
          {isExtracting && extractionProgress && (
            <div
              className="flex-shrink-0 border-b border-buddy-border bg-buddy-surface flex items-center gap-3"
              style={{ padding: "8px 48px" }}
            >
              <div className="flex-1 bg-buddy-elevated rounded-full overflow-hidden" style={{ height: 4 }}>
                <div
                  className="h-full bg-buddy-gold transition-all duration-300 rounded-full"
                  style={{ width: `${Math.round((extractionProgress.progress ?? 0) * 100)}%` }}
                />
              </div>
              <span className="text-buddy-text-dim" style={{ fontSize: 11, flexShrink: 0 }}>
                {extractionProgress.message}
              </span>
            </div>
          )}

          {/* Build progress bar (context mode) */}
          {isBuilding && (
            <div
              className="flex-shrink-0 border-b border-buddy-border bg-buddy-surface flex items-center gap-3"
              style={{ padding: "8px 48px" }}
            >
              <div className="flex-1 bg-buddy-elevated rounded-full overflow-hidden" style={{ height: 4 }}>
                <div
                  className="h-full bg-buddy-gold transition-all duration-300 rounded-full"
                  style={{ width: "60%" }}
                />
              </div>
              <span className="text-buddy-text-dim" style={{ fontSize: 11, flexShrink: 0 }}>
                Budowanie kontekstu…
              </span>
            </div>
          )}

          {/* Progress bar (chat) */}
          {progress && isLoading && (
            <div
              className="flex-shrink-0 border-b border-buddy-border bg-buddy-surface flex items-center gap-3"
              style={{ padding: "8px 48px" }}
            >
              <div className="flex-1 bg-buddy-elevated rounded-full overflow-hidden" style={{ height: 4 }}>
                <div
                  className="h-full bg-buddy-gold transition-all duration-300 rounded-full"
                  style={{ width: `${Math.round((progress.progress ?? 0) * 100)}%` }}
                />
              </div>
              <span className="text-buddy-text-dim" style={{ fontSize: 11, flexShrink: 0 }}>
                {progress.message}
              </span>
            </div>
          )}

          {/* Error banner */}
          {chatError && (
            <div
              className="flex-shrink-0 border-b border-buddy-border bg-red-900/10 text-red-400 flex items-center gap-2"
              style={{ padding: "8px 48px", fontSize: 12 }}
            >
              <span>⚠ {chatError}</span>
              <button
                onClick={clearError}
                className="ml-auto text-red-400/60 hover:text-red-400 transition-colors"
                style={{ fontSize: 14 }}
              >
                ✕
              </button>
            </div>
          )}

          {/* Messages or Requirements view */}
          <div className="flex-1 overflow-y-auto">
            {activeMode === "requirements" ? (
              <RequirementsView
                requirements={requirements}
                stats={reqStats}
                loading={reqLoading || isExtracting}
                error={reqError}
                contextReady={ragReady}
                onExtract={handleExtract}
                onMarkReviewed={handleMarkReviewed}
              />
            ) : (
              <MessageList
                messages={messages}
                isLoading={isLoading}
                glossary={ctxGlossary}
                onTermClick={handleTermClick}
              />
            )}
          </div>

          {/* Mode input box */}
          <ModeInputBox
            activeMode={activeMode}
            onModeChange={handleModeChange}
            lockedModes={[]}
            value={inputValue}
            onChange={setInputValue}
            onSend={handleSend}
            onStop={stop}
            loading={isLoading}
            attachedFiles={attachedFiles}
            onRemoveFile={(i) => setAttachedFiles((prev) => prev.filter((_, idx) => idx !== i))}
            onAttachFiles={handleAttachFiles}
          />
        </div>

        {/* ── Utility panel ─────────────────────────────────────────────────── */}
        <UtilityPanel
          open={panelOpen}
          activeMode={activeMode}
          projectId={projectId}
          projectFiles={panelFiles}
          onAddFiles={handleAttachFiles}
          onFileToggle={handleFileToggle}
          onOpenMindMap={() => setMmModalOpen(true)}
          glossary={ctxGlossary}
          onTermClick={handleUtilityTermClick}
          contextStatus={contextStatus}
          buildMode={buildMode}
          onBuildModeChange={setBuildMode}
          onBuild={handleBuild}
          heatmapData={heatmap}
          lastMappingDate={null}
          onRunMapping={() => console.log("run mapping")}
          snapshots={snapshots}
          latestSnapshotId={latestSnapshotId}
          tier={tier}
          onTierChange={(t) => {
            setTier(t);
          }}
        />
      </div>

      {/* ── Fullscreen Mind Map Modal ───────────────────────────────────────── */}
      <MindMapModal
        open={mmModalOpen}
        onClose={() => setMmModalOpen(false)}
        nodes={modalNodes}
        edges={mindMapEdges.map((e) => ({ source: e.source, target: e.target }))}
      />
    </div>
  );
}
