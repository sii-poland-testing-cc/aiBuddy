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
  const [latestSnapshotId, setLatestSnapshotId] = useState<string | undefined>();
  const abortRef = useRef<AbortController | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetStreamTimeout = (abort: AbortController) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      abort.abort();
      setError("Odpowiedź trwa zbyt długo. Spróbuj ponownie.");
    }, 120_000);
  };

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
                const { content, sources } = await formatResult(
                  event.data,
                  projectId,
                  API_BASE
                );
                assistantContent = content;
                addMessage("assistant", content, sources);
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
  }, []);

  return { messages, progress, isLoading, error, latestSnapshotId, send, stop, clear };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function formatResult(
  data: Record<string, any>,
  projectId: string,
  apiBase: string
): Promise<{ content: string; sources?: ChatSource[] }> {
  // Conversational response (no files attached)
  if (data?.message && !data?.summary) return { content: data.message };
  if (!data?.summary) return { content: JSON.stringify(data, null, 2) };

  const { summary, recommendations, next_tier, rag_sources } = data;
  const uncovered: string[] = summary.requirements_uncovered ?? [];
  const covLine = summary.requirements_total > 0
    ? `- Coverage: ${summary.coverage_pct}%  ` +
      `(${summary.requirements_covered}/${summary.requirements_total} requirements)`
    : `- Coverage: ${summary.coverage_pct}%  (no requirements found in context)`;

  const duplicatesFound: number = summary.duplicates_found ?? 0;
  const similarPairsFound: number = summary.similar_pairs_found ?? 0;
  const duplicatePairs: any[] = data.duplicates ?? [];

  const dupLines: string[] = [];
  if (duplicatesFound === 0 && similarPairsFound === 0) {
    dupLines.push(`- Duplikaty: ✅ brak`);
  } else {
    if (duplicatesFound > 0) {
      dupLines.push(`- Duplikaty: ⚠️ ${duplicatesFound} znalezionych`);
      duplicatePairs.slice(0, 3).forEach((p: any) => {
        dupLines.push(`  · ${p.tc_a} ↔ ${p.tc_b} (similarity: ${p.similarity})`);
      });
    }
    if (similarPairsFound > 0) {
      dupLines.push(`- Podobne TC: ℹ️ ${similarPairsFound} par do przeglądu`);
    }
  }

  const lines = [
    `**Audit complete ✅**`,
    ``,
    `📊 **Summary**`,
    ...dupLines,
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

  // Append diff summary if snapshot was saved
  if (data?.snapshot_id) {
    try {
      const res = await fetch(
        `${apiBase}/api/snapshots/${projectId}/latest`
      );
      if (res.ok) {
        const snap = await res.json();
        const diff = snap?.diff;
        const currPct: number = snap?.summary?.coverage_pct ?? 0;
        if (!diff) {
          lines.push(``, `📌 _Pierwszy audyt — punkt odniesienia zapisany._`);
        } else {
          const delta: number = diff.coverage_delta;
          const prevPct = +(currPct - delta).toFixed(1);
          if (delta > 0) {
            lines.push(``, `📈 **Poprawa vs poprzedni audyt**`);
            lines.push(`- Coverage: ${prevPct}% → ${currPct}% (▲ +${delta.toFixed(1)}%)`);
            if (diff.new_covered?.length)
              lines.push(`- Nowo pokryte: ${diff.new_covered.join(", ")}`);
            if (diff.newly_uncovered?.length)
              lines.push(`- ⚠️ Utracone: ${diff.newly_uncovered.join(", ")}`);
          } else if (delta < 0) {
            lines.push(``, `📉 **Regresja vs poprzedni audyt**`);
            lines.push(`- Coverage: ${prevPct}% → ${currPct}% (▼ ${delta.toFixed(1)}%)`);
            if (diff.new_covered?.length)
              lines.push(`- Nowo pokryte: ${diff.new_covered.join(", ")}`);
            if (diff.newly_uncovered?.length)
              lines.push(`- ⚠️ Utracone: ${diff.newly_uncovered.join(", ")}`);
          } else {
            lines.push(``, `📊 _Coverage bez zmian vs poprzedni audyt._`);
          }
        }
      }
    } catch {
      // diff summary is best-effort; skip on error
    }
  }

  return {
    content: lines.join("\n"),
    sources: Array.isArray(rag_sources) && rag_sources.length > 0
      ? rag_sources as ChatSource[]
      : undefined,
  };
}
