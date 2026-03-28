/**
 * useAIBuddyChat
 * ==============
 * Custom hook that connects to the FastAPI SSE stream (/api/chat/stream)
 * and maps progress + result events to React state.
 *
 * Usage:
 *   const { messages, progress, send, isLoading } = useAIBuddyChat(projectId)
 */

"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { apiFetch } from "@/lib/apiFetch";

export type MessageRole = "user" | "assistant" | "system";

export interface ChatSource {
  filename: string;
  excerpt: string;
}

export interface AuditData {
  summary: {
    coverage_pct: number;
    duplicates_found: number;
    similar_pairs_found?: number;
    untagged_cases: number;
    requirements_total: number;
    requirements_covered: number;
  };
  uncovered: string[];
  recommendations: string[];
  duplicates: Array<{ tc_a: string; tc_b: string; similarity: number | string }>;
  next_tier?: string;
  /** null = first audit (no previous); object = diff vs previous; undefined = not fetched yet */
  diff?: { coverage_delta: number; new_covered?: string[]; newly_uncovered?: string[] } | null;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  sources?: ChatSource[];
  auditData?: AuditData;
  isStatus?: boolean;  // true = pipeline status injection (no card, no sources)
}

export interface ProgressUpdate {
  message: string;
  progress: number;  // 0 – 1
}

interface UseAIBuddyChatOptions {
  projectId: string;
  tier?: "audit" | "optimize" | "regenerate" | "rag_chat";
}

const STORAGE_KEY = (projectId: string) => `ai-buddy-chat-${projectId}`;

export function useAIBuddyChat({ projectId, tier = "audit" }: UseAIBuddyChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latestSnapshotId, setLatestSnapshotId] = useState<string | undefined>();
  const abortRef = useRef<AbortController | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Restore persisted messages on mount / project change
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY(projectId));
      if (!stored) return;
      const parsed: ChatMessage[] = JSON.parse(stored);
      if (Array.isArray(parsed) && parsed.length > 0) {
        setMessages(parsed.map((m) => ({ ...m, timestamp: new Date(m.timestamp) })));
      }
    } catch {
      // storage unavailable or malformed — start fresh
    }
  }, [projectId]);

  // Persist messages on every change (skip empty to avoid wiping during init)
  useEffect(() => {
    const toSave = messages.filter((m) => !m.isStatus).slice(-100);
    if (toSave.length === 0) return;
    try {
      localStorage.setItem(STORAGE_KEY(projectId), JSON.stringify(toSave));
    } catch {
      // quota exceeded — ignore
    }
  }, [messages, projectId]);

  const resetStreamTimeout = (abort: AbortController) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      abort.abort();
      setError("Odpowiedź trwa zbyt długo. Spróbuj ponownie.");
    }, 360_000);
  };

  const addMessage = useCallback(
    (role: MessageRole, content: string, sources?: ChatSource[], auditData?: AuditData) => {
      const msg: ChatMessage = {
        id: crypto.randomUUID(),
        role,
        content,
        timestamp: new Date(),
        sources,
        auditData,
      };
      setMessages((prev) => [...prev, msg]);
      return msg;
    },
    []
  );

  const addStatusMessage = useCallback((text: string) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "assistant" as const, content: text, timestamp: new Date(), isStatus: true },
    ]);
  }, []);

  const addUserMessage = useCallback(
    (text: string) => { addMessage("user", text); },
    [addMessage]
  );

  const send = useCallback(
    async (text: string, filePaths: string[] = [], opts: { skipUserMessage?: boolean } = {}) => {
      if (!text.trim() && filePaths.length === 0) return;

      setError(null);
      if (!opts.skipUserMessage) {
        addMessage("user", text || `[Uploaded: ${filePaths.join(", ")}]`);
      }
      setIsLoading(true);
      setProgress({ message: "Łączenie…", progress: 0 });

      // Cancel any previous stream
      abortRef.current?.abort();
      const abort = new AbortController();
      abortRef.current = abort;

      try {
        const res = await apiFetch("/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_id: projectId, message: text, file_paths: filePaths, tier }),
          signal: abort.signal,
        }).catch(() => {
          throw new Error("Nie można połączyć z serwerem AI Buddy.");
        });

        if (!res.ok) throw new Error(`Nie można połączyć z serwerem AI Buddy.`);
        if (!res.body) throw new Error("Nie można połączyć z serwerem AI Buddy.");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let assistantContent = "";

        resetStreamTimeout(abort);

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          resetStreamTimeout(abort);

          const chunk = decoder.decode(value, { stream: true });
          for (const line of chunk.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.slice(6).trim();
            if (payload === "[DONE]") break;

            try {
              const event = JSON.parse(payload);

              if (event.type === "progress") {
                setProgress(event.data as ProgressUpdate);
              } else if (event.type === "result") {
                const { content, sources, auditData } = await formatResult(
                  event.data,
                  projectId
                );
                assistantContent = content;
                addMessage("assistant", content, sources, auditData);
                if (event.data?.snapshot_id) {
                  setLatestSnapshotId(event.data.snapshot_id);
                }
              } else if (event.type === "error") {
                setError(event.data.message);
                addMessage("assistant", `❌ ${event.data.message}`);
              }
            } catch {
              // malformed JSON line – skip
            }
          }
        }
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
      } catch (err: any) {
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        if (err.name !== "AbortError") {
          const msg = err.message ?? "Nie można połączyć z serwerem AI Buddy.";
          setError(msg);
          addMessage("assistant", `❌ ${msg}`);
        }
      } finally {
        setIsLoading(false);
        setProgress(null);
      }
    },
    [projectId, tier, addMessage]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
    setProgress(null);
  }, []);

  const clear = useCallback(() => {
    setMessages([]);
    setError(null);
    try { localStorage.removeItem(STORAGE_KEY(projectId)); } catch { /* ignore */ }
  }, [projectId]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return { messages, progress, isLoading, error, latestSnapshotId, send, stop, clear, clearError, addStatusMessage, addUserMessage };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Pure function: maps a raw audit result payload + fetched diff into an
 * `AuditData` shape.  Exported for unit testing.
 */
export function buildAuditData(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: Record<string, any>,
  diff: AuditData["diff"]
): AuditData {
  const { summary, recommendations, next_tier } = data;
  const uncovered: string[] = summary.requirements_uncovered ?? [];
  return {
    summary: {
      coverage_pct: summary.coverage_pct ?? 0,
      duplicates_found: summary.duplicates_found ?? 0,
      similar_pairs_found: summary.similar_pairs_found,
      untagged_cases: summary.untagged_cases ?? 0,
      requirements_total: summary.requirements_total ?? 0,
      requirements_covered: summary.requirements_covered ?? 0,
    },
    uncovered,
    recommendations: recommendations ?? [],
    duplicates: data.duplicates ?? [],
    next_tier,
    diff,
  };
}

async function formatResult(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: Record<string, any>,
  projectId: string
): Promise<{ content: string; sources?: ChatSource[]; auditData?: AuditData }> {
  // Conversational / RAG-chat response — no structured audit data
  if (data?.message && !data?.summary) return { content: data.message };
  if (!data?.summary) return { content: JSON.stringify(data, null, 2) };

  const { summary, rag_sources } = data;

  // Short intro sentence shown above the card
  const reqPart = summary.requirements_total > 0
    ? ` Sprawdziłem ${summary.requirements_total} wymagań.`
    : "";
  const content = `Audyt zakończony ✅${reqPart}`;

  // Fetch diff from the latest snapshot (best-effort)
  let diff: AuditData["diff"] = undefined;
  if (data?.snapshot_id) {
    try {
      const res = await apiFetch(`/api/snapshots/${projectId}/latest`);
      if (res.ok) {
        const snap = await res.json();
        diff = snap?.diff ?? null;   // null = first audit
      }
    } catch {
      // skip on error
    }
  }

  return {
    content,
    sources: Array.isArray(rag_sources) && rag_sources.length > 0
      ? rag_sources as ChatSource[]
      : undefined,
    auditData: buildAuditData(data, diff),
  };
}
