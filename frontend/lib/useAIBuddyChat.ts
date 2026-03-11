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

import { useState, useCallback, useRef } from "react";

export type MessageRole = "user" | "assistant" | "system";

export interface ChatSource {
  filename: string;
  excerpt: string;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  sources?: ChatSource[];
}

export interface ProgressUpdate {
  message: string;
  progress: number;  // 0 – 1
}

interface UseAIBuddyChatOptions {
  projectId: string;
  tier?: "audit" | "optimize" | "regenerate";
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function useAIBuddyChat({ projectId, tier = "audit" }: UseAIBuddyChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const addMessage = useCallback(
    (role: MessageRole, content: string, sources?: ChatSource[]) => {
      const msg: ChatMessage = {
        id: crypto.randomUUID(),
        role,
        content,
        timestamp: new Date(),
        sources,
      };
      setMessages((prev) => [...prev, msg]);
      return msg;
    },
    []
  );

  const send = useCallback(
    async (text: string, filePaths: string[] = []) => {
      if (!text.trim() && filePaths.length === 0) return;

      setError(null);
      addMessage("user", text || `[Uploaded: ${filePaths.join(", ")}]`);
      setIsLoading(true);
      setProgress({ message: "Connecting…", progress: 0 });

      // Cancel any previous stream
      abortRef.current?.abort();
      const abort = new AbortController();
      abortRef.current = abort;

      try {
        const res = await fetch(`${API_BASE}/api/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_id: projectId, message: text, file_paths: filePaths, tier }),
          signal: abort.signal,
        });

        if (!res.ok) throw new Error(`Server error: ${res.status}`);
        if (!res.body) throw new Error("No response body");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let assistantContent = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const text = decoder.decode(value, { stream: true });
          for (const line of text.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.slice(6).trim();
            if (payload === "[DONE]") break;

            try {
              const event = JSON.parse(payload);

              if (event.type === "progress") {
                setProgress(event.data as ProgressUpdate);
              } else if (event.type === "result") {
                const { content, sources } = formatResult(event.data);
                assistantContent = content;
                addMessage("assistant", content, sources);
              } else if (event.type === "error") {
                setError(event.data.message);
                addMessage("assistant", `❌ Error: ${event.data.message}`);
              }
            } catch {
              // malformed JSON line – skip
            }
          }
        }
      } catch (err: any) {
        if (err.name !== "AbortError") {
          setError(err.message);
          addMessage("assistant", `❌ Connection error: ${err.message}`);
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
  }, []);

  return { messages, progress, isLoading, error, send, stop, clear };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatResult(data: Record<string, any>): { content: string; sources?: ChatSource[] } {
  // Conversational response (no files attached)
  if (data?.message && !data?.summary) return { content: data.message };
  if (!data?.summary) return { content: JSON.stringify(data, null, 2) };

  const { summary, recommendations, next_tier, rag_sources } = data;
  const uncovered: string[] = summary.requirements_uncovered ?? [];
  const covLine = summary.requirements_total > 0
    ? `- Coverage: ${summary.coverage_pct}%  ` +
      `(${summary.requirements_covered}/${summary.requirements_total} requirements)`
    : `- Coverage: ${summary.coverage_pct}%  (no requirements found in context)`;

  const lines = [
    `**Audit complete ✅**`,
    ``,
    `📊 **Summary**`,
    `- Duplicates found: ${summary.duplicates_found}`,
    `- Untagged cases:   ${summary.untagged_cases}`,
    covLine,
    ``,
    `💡 **Recommendations**`,
    ...(recommendations ?? []).map((r: string, i: number) => `${i + 1}. ${r}`),
  ];

  if (uncovered.length > 0) {
    lines.push(``, `⚠️ **Brak pokrycia (${uncovered.length} wymagań)**`);
    uncovered.forEach((r) => lines.push(`- ${r}`));
  }

  lines.push(``, `➡️  Suggested next tier: **${next_tier?.toUpperCase()}**`);

  return {
    content: lines.join("\n"),
    sources: Array.isArray(rag_sources) && rag_sources.length > 0
      ? rag_sources as ChatSource[]
      : undefined,
  };
}
