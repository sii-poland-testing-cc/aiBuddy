"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAIBuddyChat, type ChatMessage } from "@/lib/useAIBuddyChat";
import { useProjectFiles } from "@/lib/useProjectFiles";
import { useContextBuilder } from "@/lib/useContextBuilder";
import Sidebar from "@/components/Sidebar";
import PipelineSteps from "@/components/PipelineSteps";
import MessageList from "@/components/MessageList";
import ChatInputArea from "@/components/ChatInputArea";

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

  const { messages, progress, isLoading, send, stop } = useAIBuddyChat({
    projectId,
    tier,
  });
  const { files: projectFiles, uploading, uploadFiles } = useProjectFiles(projectId);
  const { status: contextStatus } = useContextBuilder(projectId);

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
        <div className="px-6 py-3.5 border-b border-buddy-border bg-buddy-surface flex items-center gap-3 shrink-0">
          <div className="min-w-0 shrink-0">
            <div className="text-[15px] font-semibold text-buddy-text truncate">{projectId}</div>
            <div className="text-xs text-buddy-text-dim">Test Suite Audit &amp; Optimization</div>
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

        <MessageList
          messages={displayMessages}
          isLoading={isLoading}
          lastMessageId={lastMessageId}
        />

        <ChatInputArea
          onSend={send}
          onStop={stop}
          isLoading={isLoading}
          onUploadFiles={uploadFiles}
          isUploading={uploading}
        />
      </div>
    </div>
  );
}
