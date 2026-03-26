"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useParams, useSearchParams } from "next/navigation";
import TopBar from "@/components/TopBar";
import MessageList from "@/components/MessageList";
import ModeInputBox from "@/components/ModeInputBox";
import UtilityPanel from "@/components/UtilityPanel";
import { ProgressBar } from "@/components/ProgressBar";
import MindMapModal from "@/components/MindMapModal";
import { layoutModalNodes } from "@/lib/mindMapLayout";
import { useAIBuddyChat } from "@/lib/useAIBuddyChat";
import { useAuditPipeline } from "@/lib/useAuditPipeline";
import { useContextBuilder } from "@/lib/useContextBuilder";
import type { GlossaryTerm as ContextGlossaryTerm } from "@/lib/useContextBuilder";
import { useProjectFiles } from "@/lib/useProjectFiles";
import { useHeatmap } from "@/lib/useHeatmap";
import { useMapping } from "@/lib/useMapping";
import { useRequirements } from "@/lib/useRequirements";
import { useWorkContext } from "@/lib/useWorkContext";
import type { WorkContext } from "@/lib/useWorkContext";
import { usePromotion, type PromotionResult } from "@/lib/usePromotion";
import { useConflicts } from "@/lib/useConflicts";
import PromotionPreview from "@/components/PromotionPreview";
import ConflictResolution from "@/components/ConflictResolution";
import { useSnapshots } from "@/lib/useSnapshots";
import { usePanelFiles } from "@/lib/usePanelFiles";
import { useJira } from "./useJira";
import RequirementsView from "@/components/RequirementsView";
import InfoBanner from "@/components/InfoBanner";
import WorkContextBar from "@/components/WorkContextBar";

type Mode = "context" | "requirements" | "audit";
type Tier = "audit" | "optimize" | "regenerate" | "rag_chat";
type BuildMode = "append" | "rebuild";

interface AttachedFile {
  name: string;
  path: string;  // full server-side path returned by uploadFiles
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
  const contextFileInputRef = useRef<HTMLInputElement>(null);
  const [pendingContextFiles, setPendingContextFiles] = useState<File[]>([]);

  // ── Hooks ───────────────────────────────────────────────────────────────────
  const {
    messages, progress, isLoading, error: chatError,
    latestSnapshotId, send, stop, clearError, addStatusMessage, addUserMessage,
  } = useAIBuddyChat({ projectId, tier });

  const {
    result: ctxResult, status: contextStatus,
    isBuilding, buildContext, fetchStatus,
    statusError: contextStatusError, clearStatusError: clearContextStatusError,
    noopMessage: contextNoopMessage, clearNoopMessage: clearContextNoopMessage,
  } = useContextBuilder(projectId);

  const { uploadFiles } = useProjectFiles(projectId);
  const { heatmap, retry: retryHeatmap } = useHeatmap(projectId);
  const {
    isRunning: isMappingRunning,
    progress: mappingProgress,
    lastRunAt: lastMappingDate,
    runMapping,
  } = useMapping(projectId, retryHeatmap);
  const {
    contexts: workContexts,
    currentContextId,
    setContext: setCurrentContextId,
    createContext: createWorkContext,
    createDomain: createWorkDomain,
    updateContext: updateWorkContext,
    archiveContext: archiveWorkContext,
    refresh: refreshWorkContexts,
  } = useWorkContext(projectId);

  // ── Promotion & Conflicts ────────────────────────────────────────────────────
  const { pendingCount: pendingConflicts, refresh: refreshConflicts } = useConflicts(projectId);
  const [promotionContext, setPromotionContext] = useState<WorkContext | null>(null);
  const [promotionResult, setPromotionResult] = useState<{
    count: number;
    conflicts: number;
    contextName: string;
  } | null>(null);
  const [conflictViewOpen, setConflictViewOpen] = useState(false);

  const {
    requirements, stats: reqStats, loading: reqLoading, error: reqError,
    isExtracting, extractionProgress,
    extractRequirements, patchRequirement,
  } = useRequirements(projectId, {
    workContextId: currentContextId,
    includePending: currentContextId != null,
  });

  const snapshots = useSnapshots(projectId, latestSnapshotId);
  const [panelFiles, handleFileToggle] = usePanelFiles(projectId, refreshKey);

  const itemCounts = useMemo(() => {
    const counts: Record<string, { reqs: number; audits: number }> = {};
    for (const req of requirements) {
      if (req.work_context_id) {
        counts[req.work_context_id] ??= { reqs: 0, audits: 0 };
        counts[req.work_context_id].reqs++;
      }
    }
    for (const snap of snapshots) {
      if (snap.work_context_id) {
        counts[snap.work_context_id] ??= { reqs: 0, audits: 0 };
        counts[snap.work_context_id].audits++;
      }
    }
    return counts;
  }, [requirements, snapshots]);

  const getSelectedFilePaths = useCallback(
    () => panelFiles.filter((f) => f.selected).map((f) => f.file_path),
    [panelFiles]
  );

  const { handleAuditPipeline } = useAuditPipeline({
    projectId,
    extractRequirements,
    isExtracting,
    runMapping,
    isMappingRunning,
    send,
    addUserMessage,
    addStatusMessage,
    getSelectedFilePaths,
  });

  // Refresh panel files + snapshots after audit completes
  useEffect(() => {
    if (latestSnapshotId) setRefreshKey((k) => k + 1);
  }, [latestSnapshotId]);

  // Refresh context status on mount
  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const onFilesChanged = useCallback(() => setRefreshKey((k) => k + 1), []);

  const {
    projectSettings,
    contextJiraItems,
    addJiraIssue: handleAddJira,
    deleteJiraIssue: handleDeleteJiraIssue,
    deleteFile: handleDeleteFile,
  } = useJira({
    projectId,
    activeMode,
    jiraSources: contextStatus?.jira_sources,
    fetchStatus,
    onFilesChanged,
  });

  // ── Derived data ────────────────────────────────────────────────────────────
  const mindMapNodes = ctxResult?.mind_map?.nodes ?? [];
  const mindMapEdges = ctxResult?.mind_map?.edges ?? [];
  // Pre-computed layout for fullscreen modal (dagre x/y + depth)
  const modalNodes = layoutModalNodes(mindMapNodes, mindMapEdges);
  const ctxGlossary: ContextGlossaryTerm[] = ctxResult?.glossary ?? [];
  const ragReady = contextStatus?.rag_ready ?? false;

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleBuild = useCallback(
    async (mode: BuildMode) => {
      await buildContext(pendingContextFiles, mode);
      setPendingContextFiles([]);
    },
    [buildContext, pendingContextFiles]
  );

  const handleContextAddFiles = useCallback(() => {
    contextFileInputRef.current?.click();
  }, []);

  const handleContextFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      if (!files.length) return;
      setPendingContextFiles((prev) => {
        const existingNames = new Set(prev.map((f) => f.name));
        return [...prev, ...files.filter((f) => !existingNames.has(f.name))];
      });
      if (contextFileInputRef.current) contextFileInputRef.current.value = "";
    },
    []
  );

  // Matches: "rebuild", "rebuild context", "przebuduj kontekst", "odbuduj kontekst", etc.
  const REBUILD_RE = /^(rebuild(\s+(context|kontekst))?|przebuduj(\s+kontekst)?|odbuduj(\s+kontekst)?)$/i;

  const handleSend = useCallback(async () => {
    if (!inputValue.trim() && attachedFiles.length === 0) return;

    // Context mode: intercept rebuild chat commands → trigger context rebuild
    if (activeMode === "context" && REBUILD_RE.test(inputValue.trim())) {
      setInputValue("");
      await handleBuild(buildMode);
      return;
    }

    const messageText = inputValue;
    const attachedPaths = attachedFiles.map((f) => f.path);
    setInputValue("");
    setAttachedFiles([]);

    // Audit mode: run full pipeline (requirements → mapping → audit) if needed
    if (activeMode === "audit") {
      await handleAuditPipeline(messageText, attachedPaths);
      return;
    }

    // Context mode: never include audit panel files
    const selectedPaths = activeMode !== "context"
      ? panelFiles.filter((f) => f.selected).map((f) => f.file_path)
      : [];
    await send(messageText, [...selectedPaths, ...attachedPaths]);
  }, [inputValue, attachedFiles, panelFiles, send, activeMode, buildMode, handleBuild, handleAuditPipeline]);

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
        ...files.map((f, i) => ({ name: f.name, path: paths[i] ?? f.name })),
      ]);
      setRefreshKey((k) => k + 1);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [uploadFiles]
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

  const handlePromoteContext = useCallback((ctx: WorkContext) => {
    setPromotionContext(ctx);
  }, []);

  const handlePromotionConfirm = useCallback(
    async (result: PromotionResult, ctxName: string) => {
      setPromotionContext(null);
      setPromotionResult({
        count: result.promoted_count,
        conflicts: result.conflict_count,
        contextName: ctxName,
      });
      await refreshWorkContexts();
      if (result.conflict_count > 0) refreshConflicts();
    },
    [refreshWorkContexts, refreshConflicts],
  );


  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col bg-buddy-base" style={{ height: "100vh" }}>

      {/* Hidden file input for test-file attachment (M2) */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".xlsx,.csv,.json,.pdf,.feature,.txt,.md"
        className="hidden"
        onChange={handleFileInputChange}
      />

      {/* Hidden file input for context documents (M1 — .docx/.pdf only) */}
      <input
        ref={contextFileInputRef}
        type="file"
        multiple
        accept=".docx,.pdf"
        className="hidden"
        onChange={handleContextFileInputChange}
      />

      {/* ── TopBar ─────────────────────────────────────────────────────────── */}
      <TopBar
        projectId={projectId}
        onTogglePanel={() => setPanelOpen((o) => !o)}
        panelOpen={panelOpen}
        ragReady={ragReady}
      />

      {/* ── Work Context Bar ────────────────────────────────────────────────── */}
      <WorkContextBar
        projectId={projectId}
        contexts={workContexts}
        currentContextId={currentContextId}
        onContextChange={setCurrentContextId}
        createContext={createWorkContext}
        createDomain={createWorkDomain}
        updateContext={updateWorkContext}
        archiveContext={archiveWorkContext}
        itemCounts={itemCounts}
        pendingConflicts={pendingConflicts}
        onOpenConflicts={() => setConflictViewOpen(true)}
        onPromote={handlePromoteContext}
      />

      {/* ── Main: chat + artifact + utility ────────────────────────────────── */}
      <div
        className="flex overflow-hidden"
        style={{ flex: 1, marginTop: 84 }}
      >

        {/* ── Chat column ──────────────────────────────────────────────────── */}
        <div className="flex flex-col flex-1 min-w-0 overflow-hidden">

          {/* Progress bars */}
          <ProgressBar
            visible={isExtracting && !!extractionProgress}
            progress={extractionProgress?.progress}
            message={extractionProgress?.message}
          />
          <ProgressBar
            visible={isBuilding}
            message="Budowanie kontekstu…"
          />
          <ProgressBar
            visible={!!(progress && isLoading)}
            progress={progress?.progress}
            message={progress?.message}
          />

          {/* Context status error banner (backend offline on mount) */}
          {contextStatusError && (
            <div
              className="flex-shrink-0 border-b border-buddy-border flex items-center gap-2"
              style={{ padding: "8px 48px", fontSize: 12, background: "rgba(200,144,42,0.08)", color: "#c8902a" }}
            >
              <span>⚠ {contextStatusError}</span>
              <button
                onClick={clearContextStatusError}
                className="ml-auto hover:opacity-70 transition-opacity"
                style={{ fontSize: 14 }}
              >
                ✕
              </button>
            </div>
          )}

          {/* Context build noop banner (all files already indexed) */}
          {contextNoopMessage && activeMode === "context" && (
            <div className="flex-shrink-0 border-b border-buddy-border" style={{ padding: "6px 48px" }}>
              <InfoBanner message={contextNoopMessage} onDismiss={clearContextNoopMessage} />
            </div>
          )}

          {/* Chat error banner */}
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

          {/* Promotion result banner */}
          {promotionResult && (
            <div
              className="flex-shrink-0 border-b border-buddy-border flex items-center gap-2"
              style={{
                padding: "8px 48px",
                fontSize: 12,
                background: "rgba(74,158,107,0.08)",
                color: "#4a9e6b",
              }}
            >
              <span>
                ✓ Promoted {promotionResult.count} item
                {promotionResult.count !== 1 ? "s" : ""} from &quot;
                {promotionResult.contextName}&quot;
                {promotionResult.conflicts > 0
                  ? `. ${promotionResult.conflicts} conflict${promotionResult.conflicts !== 1 ? "s" : ""} queued for review.`
                  : "."}
              </span>
              {promotionResult.conflicts > 0 && (
                <button
                  onClick={() => {
                    setPromotionResult(null);
                    setConflictViewOpen(true);
                  }}
                  className="text-buddy-gold hover:text-buddy-gold-light underline transition-colors"
                  style={{ fontSize: 11 }}
                >
                  View conflicts →
                </button>
              )}
              <button
                onClick={() => setPromotionResult(null)}
                className="ml-auto text-buddy-success/60 hover:text-buddy-success"
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
                currentContextId={currentContextId}
                contexts={workContexts}
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
          onAuditPipeline={handleAuditPipeline}
          auditFiles={panelFiles}
          pendingContextFiles={pendingContextFiles.map((f) => f.name)}
          onAddFiles={activeMode === "context" ? handleContextAddFiles : handleAttachFiles}
          onFileToggle={handleFileToggle}
          onOpenMindMap={() => setMmModalOpen(true)}
          glossary={ctxGlossary}
          onTermClick={handleUtilityTermClick}
          contextStatus={contextStatus}
          buildMode={buildMode}
          onBuildModeChange={setBuildMode}
          onBuild={handleBuild}
          isBuildRunning={isBuilding}
          heatmapData={heatmap}
          lastMappingDate={lastMappingDate}
          isMappingRunning={isMappingRunning}
          mappingProgress={mappingProgress}
          onRunMapping={runMapping}
          snapshots={snapshots}
          latestSnapshotId={latestSnapshotId}
          tier={tier}
          onTierChange={(t) => {
            setTier(t);
          }}
          workContexts={workContexts}
          currentContextId={currentContextId}
          onContextChange={setCurrentContextId}
          jiraItems={activeMode === "context" ? contextJiraItems : undefined}
          onAddJiraIssue={handleAddJira}
          onDeleteJiraIssue={handleDeleteJiraIssue}
          onDeleteFile={handleDeleteFile}
          projectSettings={projectSettings}
        />
      </div>

      {/* ── Fullscreen Mind Map Modal ───────────────────────────────────────── */}
      <MindMapModal
        open={mmModalOpen}
        onClose={() => setMmModalOpen(false)}
        nodes={modalNodes}
        edges={mindMapEdges.map((e) => ({ source: e.source, target: e.target }))}
        currentContextId={currentContextId}
        contexts={workContexts}
      />

      {/* ── Promotion Preview Modal ─────────────────────────────────────────── */}
      {promotionContext && (
        <PromotionPreview
          projectId={projectId}
          context={promotionContext}
          parentName={
            promotionContext.parent_id
              ? (workContexts.find((c) => c.id === promotionContext.parent_id)?.name ?? "parent")
              : "Domain"
          }
          onConfirm={(result) => handlePromotionConfirm(result, promotionContext.name)}
          onCancel={() => setPromotionContext(null)}
        />
      )}

      {/* ── Conflict Resolution Overlay ─────────────────────────────────────── */}
      <ConflictResolution
        open={conflictViewOpen}
        onClose={() => {
          setConflictViewOpen(false);
          refreshConflicts();
        }}
        projectId={projectId}
        initialContextId={currentContextId}
      />
    </div>
  );
}
