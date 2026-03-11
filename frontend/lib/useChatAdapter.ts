"use client";

/**
 * useChatAdapter
 * ==============
 * Bridges useAIBuddyChat (custom SSE hook) into the shape that
 * @llamaindex/chat-ui's ChatSection expects (compatible with
 * @ai-sdk/react's UseChatHelpers interface).
 */

import { useState, useCallback } from "react";
import { useAIBuddyChat } from "./useAIBuddyChat";

interface ChatAdapterOptions {
  projectId: string;
  tier?: "audit" | "optimize" | "regenerate";
}

export function useChatAdapter({
  projectId,
  tier = "audit",
}: ChatAdapterOptions) {
  const { messages, progress, isLoading, error, send, stop, clear } =
    useAIBuddyChat({ projectId, tier });

  const [input, setInput] = useState("");

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setInput(e.target.value);
    },
    []
  );

  const handleSubmit = useCallback(
    (e?: { preventDefault?: () => void }) => {
      e?.preventDefault?.();
      const text = input.trim();
      if (!text) return;
      send(text);
      setInput("");
    },
    [input, send]
  );

  const append = useCallback(
    async (message: { role: string; content: string }) => {
      await send(message.content);
      return null;
    },
    [send]
  );

  // Map to the shape ChatSection reads via its internal context
  const handler = {
    messages: messages.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      createdAt: m.timestamp,
      parts: [{ type: "text" as const, text: m.content }],
    })),
    input,
    setInput,
    handleInputChange,
    handleSubmit,
    isLoading,
    status: (error ? "error" : isLoading ? "streaming" : "ready") as
      | "error"
      | "streaming"
      | "submitted"
      | "ready",
    stop,
    append,
    reload: async () => null as string | null | undefined,
    setMessages: () => {},
    error: error ? new Error(error) : undefined,
    data: undefined,
  };

  return { handler, progress, isLoading, clear };
}
