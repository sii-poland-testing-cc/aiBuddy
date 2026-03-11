"use client";

import { useRef, useEffect, useState } from "react";
import type { ChatMessage, ChatSource } from "@/lib/useAIBuddyChat";

// ── Sub-components ─────────────────────────────────────────────────────────────

function BotAvatar() {
  return (
    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-buddy-gold to-buddy-gold-light flex items-center justify-center text-sm font-bold text-buddy-surface shrink-0 mt-0.5">
      Q
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-2.5 mb-4">
      <BotAvatar />
      <div className="bg-buddy-elevated rounded-[4px_18px_18px_18px] border border-buddy-border-dark px-4 py-2">
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-buddy-gold"
              style={{ animation: `bounce 1.2s ${i * 0.2}s infinite` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

/** Renders text with **bold** and `code` inline markers. */
function renderContent(text: string) {
  return text.split("\n").map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return (
      <div key={i} className={/^(\d+\.|-)/.test(line.trimStart()) ? "pl-3" : ""}>
        {parts.map((part, j) => {
          if (part.startsWith("**") && part.endsWith("**")) {
            return (
              <strong key={j} className="font-semibold text-buddy-gold-light">
                {part.slice(2, -2)}
              </strong>
            );
          }
          if (part.startsWith("`") && part.endsWith("`")) {
            return (
              <code key={j} className="font-mono text-xs bg-buddy-border px-1 rounded text-buddy-gold">
                {part.slice(1, -1)}
              </code>
            );
          }
          return <span key={j}>{part || "\u00A0"}</span>;
        })}
      </div>
    );
  });
}

// ── Sources panel ──────────────────────────────────────────────────────────────

function SourcesPanel({ sources }: { sources: ChatSource[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 border-t border-buddy-border pt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-[11px] text-buddy-text-dim hover:text-buddy-text-muted transition-colors"
      >
        <span className={`transition-transform duration-150 ${open ? "rotate-90" : ""}`}>▶</span>
        Źródła ({sources.length})
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {sources.map((s, i) => {
            const ext = s.filename.split(".").pop()?.toUpperCase() ?? "FILE";
            return (
              <div key={i} className="bg-buddy-base rounded-md border border-buddy-border px-3 py-2 text-[11px] space-y-1">
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-buddy-gold opacity-60">{ext}</span>
                  <span className="text-buddy-text-muted font-medium truncate">{s.filename}</span>
                </div>
                <p className="text-buddy-text-dim leading-relaxed line-clamp-2">{s.excerpt}</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── MessageList ────────────────────────────────────────────────────────────────

interface MessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
  lastMessageId?: string;
}

export default function MessageList({
  messages,
  isLoading,
  lastMessageId,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div className="flex-1 overflow-y-auto px-[60px] py-6">
      {messages.map((msg) => {
        const isUser = msg.role === "user";
        const isNew = msg.id === lastMessageId;
        return (
          <div
            key={msg.id}
            className={`flex mb-4 ${isUser ? "justify-end" : "justify-start"} ${isNew ? "animate-fade-up" : ""}`}
          >
            {!isUser && <BotAvatar />}
            <div
              className={`max-w-[72%] text-sm leading-relaxed whitespace-pre-wrap ${
                isUser
                  ? "ml-4 bg-gradient-to-br from-buddy-gold to-buddy-gold-light text-buddy-surface rounded-[18px_18px_4px_18px] px-4 py-2.5"
                  : "ml-2.5 bg-buddy-elevated text-buddy-text rounded-[4px_18px_18px_18px] px-4 py-2.5 border border-buddy-border"
              }`}
            >
              {renderContent(msg.content)}
              {!isUser && msg.sources && msg.sources.length > 0 && (
                <SourcesPanel sources={msg.sources} />
              )}
            </div>
          </div>
        );
      })}
      {isLoading && <TypingIndicator />}
      <div ref={endRef} />
    </div>
  );
}
