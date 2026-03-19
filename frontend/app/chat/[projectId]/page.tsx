"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAIBuddyChat, type ChatMessage } from "@/lib/useAIBuddyChat";
import { useProjectFiles } from "@/lib/useProjectFiles";
import { useContextBuilder } from "@/lib/useContextBuilder";
import Sidebar from "@/components/Sidebar";
import ErrorBanner from "@/components/ErrorBanner";
import PipelineSteps from "@/components/PipelineSteps";
import MessageList from "@/components/MessageList";
import ChatInputArea from "@/components/ChatInputArea";
import AuditFileSelector from "@/components/AuditFileSelector";
import AuditHistory from "@/components/AuditHistory";

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "Cześć! Jestem **AI Buddy** — Twój asystent QA. Wgraj zestaw testów lub zacznij od audytu istniejącego projektu.\n\nMogę:\n- 🔍 **Audytować** suite testów i wskazać luki\n- ⚙️ **Optymalizować** tagi, priorytety i pokrycie\n- 🔄 **Regenerować** przypadki testowe na podstawie dokumentacji",
  timestamp: new Date(),
};

export default function ChatPage({
  params,
}: {
  params: { projectId: string };
}) {
  const projectId = decodeURIComponent(params.projectId);
  const router = useRouter();
  const [tier, setTier] = useState<"audit" | "optimize" | "regenerate">(
    "audit"
  );
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const prevLoadingRef = useRef(false);

  const { messages, progress, isLoading, error: chatError, latestSnapshotId, send, stop, clearError } = useAIBuddyChat({
    projectId,
    tier,
  });
  const { files: projectFiles, uploading, uploadFiles, uploadError, clearUploadError } = useProjectFiles(projectId);
  const { status: contextStatus } = useContextBuilder(projectId);

  // Refresh file selector after audit completes
  useEffect(() => {
    if (prevLoadingRef.current && !isLoading) {
      setRefreshKey((k) => k + 1);
    }
    prevLoadingRef.current = isLoading;
  }, [isLoading]);

  // Wrap send to inject selected files from the selector
  const handleSend = useCallback(
    (text: string, filePaths: string[] = []) => {
      send(text, [...selectedFiles, ...filePaths]);
    },
    [send, selectedFiles]
  );

  const displayMessages =
    messages.length === 0 ? [WELCOME] : [WELCOME, ...messages];
  const lastMessageId = messages[messages.length - 1]?.id;

  return (
    <div className="flex h-screen overflow-hidden bg-buddy-base text-buddy-text font-sans">
      <Sidebar
        activeProjectId={projectId}
        projectFiles={projectFiles}
        onUploadFiles={uploadFiles}
        isUploading={uploading}
        contextReady={contextStatus?.rag_ready}
        activeModule="m2"
      />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="pl-14 md:pl-6 pr-6 py-3.5 border-b border-buddy-border bg-buddy-surface flex items-center gap-3 shrink-0">
          <div className="min-w-0 shrink-0">
            <div className="text-[15px] font-semibold text-buddy-text truncate">{projectId}</div>
            <div className="text-xs text-buddy-text-dim">Audyt i optymalizacja zestawu testów</div>
          </div>

          {/* Context status badge */}
          {contextStatus?.rag_ready ? (
            <div className="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 rounded-full px-2.5 py-1 shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              Kontekst gotowy
              {contextStatus.stats?.entity_count != null && (
                <span className="text-emerald-400/70">· {contextStatus.stats.entity_count} encji</span>
              )}
            </div>
          ) : contextStatus ? (
            <button
              onClick={() => router.push(`/context/${encodeURIComponent(projectId)}`)}
              className="flex items-center gap-1.5 text-xs text-buddy-gold bg-buddy-gold/5 border border-buddy-gold/20 rounded-full px-2.5 py-1 hover:bg-buddy-gold/10 transition-colors shrink-0"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-buddy-gold animate-pulse" />
              Brak kontekstu — przejdź do M1
            </button>
          ) : null}

          <div className="flex-1" />
          <PipelineSteps activeTier={tier} onTierChange={setTier} />
        </div>

        {/* Workflow progress bar */}
        {progress && (
          <div className="px-6 py-2 bg-buddy-gold/10 border-b border-buddy-border shrink-0">
            <div className="flex justify-between text-xs text-buddy-gold mb-1">
              <span>{progress.message}</span>
              <span>{Math.round(progress.progress * 100)}%</span>
            </div>
            <div className="w-full h-0.5 bg-buddy-border rounded-full overflow-hidden">
              <div
                className="h-full bg-buddy-gold rounded-full transition-all duration-300"
                style={{ width: `${progress.progress * 100}%` }}
              />
            </div>
          </div>
        )}

        {chatError && (
          <div className="mx-6 mt-3 shrink-0">
            <ErrorBanner message={chatError} onDismiss={() => clearError()} />
          </div>
        )}

        {uploadError && (
          <div className="mx-6 mt-3 shrink-0">
            <ErrorBanner message={uploadError} onDismiss={clearUploadError} />
          </div>
        )}

        {projectFiles.length === 0 && !uploading && (
          <div className="mx-6 mt-3 shrink-0">
            <div className="flex flex-col items-center gap-3 px-6 py-6 rounded-xl bg-buddy-elevated border border-buddy-border text-center">
              <span className="text-3xl leading-none">📂</span>
              <div>
                <p className="text-sm font-medium text-buddy-text mb-1">
                  Wgraj pliki testowe, aby rozpocząć audyt
                </p>
                <p className="text-xs text-buddy-text-muted leading-relaxed max-w-sm">
                  Przeciągnij pliki lub użyj przycisku poniżej. Dla najlepszych wyników, najpierw{" "}
                  <button
                    onClick={() => router.push(`/context/${encodeURIComponent(projectId)}`)}
                    className="text-buddy-gold hover:text-buddy-gold-light underline underline-offset-2 transition-colors"
                  >
                    zbuduj kontekst
                  </button>{" "}
                  i{" "}
                  <button
                    onClick={() => router.push(`/requirements/${encodeURIComponent(projectId)}`)}
                    className="text-buddy-gold hover:text-buddy-gold-light underline underline-offset-2 transition-colors"
                  >
                    wyodrębnij wymagania
                  </button>
                  .
                </p>
              </div>
              <button
                onClick={() => uploadFiles([]).catch(() => {})}
                className="px-4 py-2 bg-gradient-to-r from-buddy-gold to-buddy-gold-light text-buddy-surface text-xs font-semibold rounded-lg hover:opacity-90 transition-opacity"
              >
                Wgraj pliki testowe
              </button>
            </div>
          </div>
        )}

        <MessageList
          messages={displayMessages}
          isLoading={isLoading}
          lastMessageId={lastMessageId}
        />

        <div className="shrink-0 max-h-[200px] overflow-y-auto">
          <AuditFileSelector
            projectId={projectId}
            onSelectionChange={setSelectedFiles}
            refreshKey={refreshKey}
          />

          <AuditHistory
            projectId={projectId}
            latestSnapshotId={latestSnapshotId}
          />
        </div>

        <ChatInputArea
          onSend={handleSend}
          onStop={stop}
          isLoading={isLoading}
          onUploadFiles={uploadFiles}
          isUploading={uploading}
        />
      </div>
    </div>
  );
}
