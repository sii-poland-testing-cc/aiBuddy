"use client";

import { useRef, useEffect } from "react";
import type { ChatMessage } from "@/lib/useAIBuddyChat";
import type { GlossaryTerm } from "@/components/Glossary";
import { parseRelatedTerms } from "@/lib/parseRelatedTerms";
import { AuditResultCard } from "@/components/AuditResultCard";

// ── Avatars ───────────────────────────────────────────────────────────────────

function BotAvatar() {
  return (
    <div
      className="rounded-full bg-buddy-gold flex items-center justify-center font-bold text-buddy-surface shrink-0"
      style={{ width: 28, height: 28, fontSize: 10, marginTop: 2 }}
    >
      A
    </div>
  );
}

// ── Typing indicator ──────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex items-start gap-2.5 mb-4">
      <BotAvatar />
      <div
        className="bg-buddy-surface border border-buddy-border"
        style={{ borderRadius: "2px 10px 10px 10px", padding: "10px 14px" }}
      >
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="rounded-full bg-buddy-gold"
              style={{
                width: 6, height: 6,
                animation: `think 1.2s ${i * 0.2}s infinite`,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Text rendering ────────────────────────────────────────────────────────────

function renderContent(text: string) {
  return text.split("\n").map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return (
      <div key={i} className={/^(\d+\.|-)/.test(line.trimStart()) ? "pl-3" : ""}>
        {parts.map((part, j) => {
          if (part.startsWith("**") && part.endsWith("**"))
            return <strong key={j} className="font-semibold text-buddy-gold-light">{part.slice(2, -2)}</strong>;
          if (part.startsWith("`") && part.endsWith("`"))
            return <code key={j} className="font-mono bg-buddy-border px-1 rounded text-buddy-gold" style={{ fontSize: 11 }}>{part.slice(1, -1)}</code>;
          return <span key={j}>{part || "\u00A0"}</span>;
        })}
      </div>
    );
  });
}

// Matches "**Powiązane terminy**" with optional capital T and optional trailing
// colon/dash — handles the most likely LLM formatting drift.
const RELATED_MARKER_RE = /\*\*Powiązane [Tt]erminy\*\*\s*[—–:-]?/;

function renderAssistantContent(
  text: string,
  glossary: GlossaryTerm[],
  onTermClick?: (term: GlossaryTerm) => void,
) {
  const match = RELATED_MARKER_RE.exec(text);
  if (!match) return renderContent(text);

  const markerIdx = match.index;
  const before = text.slice(0, markerIdx);
  const afterMarker = text.slice(markerIdx + match[0].length);
  const firstNewline = afterMarker.indexOf("\n");
  const termsLine = (firstNewline === -1 ? afterMarker : afterMarker.slice(0, firstNewline))
    .replace(/^\s*[—–-]\s*/, "").trim();
  const remaining = firstNewline === -1 ? "" : afterMarker.slice(firstNewline + 1).trim();
  const chunks = parseRelatedTerms(termsLine, glossary);

  return (
    <>
      {renderContent(before)}
      <div>
        <strong className="font-semibold text-buddy-gold-light">Powiązane terminy</strong>
        {" — "}
        {chunks.map((chunk, i) =>
          chunk.isGlossaryTerm && onTermClick ? (
            <span
              key={i}
              role="button"
              tabIndex={0}
              onClick={() => onTermClick(chunk.glossaryItem!)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onTermClick(chunk.glossaryItem!); } }}
              style={{ cursor: "pointer", color: "#f0c060", borderBottom: "1px dashed #c8902a", fontWeight: 600, marginRight: 6 }}
            >
              {chunk.text}
            </span>
          ) : (
            <span key={i} style={{ marginRight: 6 }}>{chunk.text}</span>
          )
        )}
      </div>
      {remaining && renderContent(remaining)}
    </>
  );
}

// ── MessageList ───────────────────────────────────────────────────────────────

interface MessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
  lastMessageId?: string;
  onTermClick?: (term: GlossaryTerm) => void;
  glossary?: GlossaryTerm[];
}

export default function MessageList({
  messages,
  isLoading,
  lastMessageId,
  onTermClick,
  glossary = [],
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "24px 48px 16px", display: "flex", flexDirection: "column", gap: 16 }}>
      <style>{`
        @keyframes think { 0%,60%,100% { opacity: 0.2; transform: scale(0.8); } 30% { opacity: 1; transform: scale(1); } }
      `}</style>

      {messages.map((msg) => {
        const isUser = msg.role === "user";
        return (
          <div key={msg.id} className={`flex ${isUser ? "flex-row-reverse" : "flex-row"} gap-2.5`}>
            {!isUser && <BotAvatar />}

            {isUser ? (
              <div
                className="text-buddy-surface"
                style={{
                  maxWidth: "68%", padding: "10px 14px",
                  borderRadius: "10px 2px 10px 10px",
                  background: "#2a2520", border: "1px solid #3a342c",
                  fontSize: 13, lineHeight: 1.6, color: "#e8dcc8",
                }}
              >
                {renderContent(msg.content)}
              </div>
            ) : (
              <div style={{ maxWidth: "80%", display: "flex", flexDirection: "column" }}>
                {/* Bubble */}
                <div
                  style={{
                    padding: "10px 14px",
                    borderRadius: "2px 10px 10px 10px",
                    background: "#1a1612", border: "1px solid #2a2520",
                    fontSize: 13, lineHeight: 1.6, color: "#e8dcc8",
                  }}
                >
                  {renderAssistantContent(msg.content, glossary, onTermClick)}
                </div>

                {/* Audit result card (rendered outside bubble for visual separation) */}
                {msg.auditData && (
                  <AuditResultCard data={msg.auditData} sources={msg.sources} />
                )}
              </div>
            )}
          </div>
        );
      })}

      {isLoading && <TypingIndicator />}
      <div ref={endRef} />
    </div>
  );
}
