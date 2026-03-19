"use client";

import { useRef, useEffect, useState } from "react";
import type { ChatMessage, ChatSource, AuditData } from "@/lib/useAIBuddyChat";
import type { GlossaryTerm } from "@/components/Glossary";
import { parseRelatedTerms } from "@/lib/parseRelatedTerms";

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

const RELATED_MARKER = "**Powiązane terminy**";

function renderAssistantContent(
  text: string,
  glossary: GlossaryTerm[],
  onTermClick?: (term: GlossaryTerm) => void,
) {
  const markerIdx = text.indexOf(RELATED_MARKER);
  if (markerIdx === -1) return renderContent(text);

  const before = text.slice(0, markerIdx);
  const afterMarker = text.slice(markerIdx + RELATED_MARKER.length);
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

// ── Audit result card ─────────────────────────────────────────────────────────

function coverageColor(pct: number) {
  if (pct >= 80) return "#4a9e6b";
  if (pct >= 50) return "#f0c060";
  return "#c0504a";
}

function Metric({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <div style={{ fontSize: 10, color: "#6a5f50", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, fontFamily: "monospace", color: color ?? "#e8dcc8" }}>{value}</div>
    </div>
  );
}

function DiffBadge({ diff }: { diff: AuditData["diff"] }) {
  if (diff === undefined) return null;
  if (diff === null) {
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 7px", borderRadius: 20, fontSize: 11, fontWeight: 700, fontFamily: "monospace", background: "rgba(106,95,80,0.3)", color: "#a09078" }}>
        📌 Pierwszy
      </span>
    );
  }
  const delta = diff.coverage_delta ?? 0;
  if (Math.abs(delta) < 0.05) {
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 7px", borderRadius: 20, fontSize: 11, fontWeight: 700, fontFamily: "monospace", background: "rgba(106,95,80,0.3)", color: "#a09078" }}>
        → 0%
      </span>
    );
  }
  if (delta > 0) {
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 7px", borderRadius: 20, fontSize: 11, fontWeight: 700, fontFamily: "monospace", background: "rgba(74,158,107,0.2)", color: "#4a9e6b" }}>
        ▲ +{delta.toFixed(1)}%
      </span>
    );
  }
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 7px", borderRadius: 20, fontSize: 11, fontWeight: 700, fontFamily: "monospace", background: "rgba(192,80,74,0.2)", color: "#c0504a" }}>
      ▼ {delta.toFixed(1)}%
    </span>
  );
}

function AuditResultCard({ data, sources }: { data: AuditData; sources?: ChatSource[] }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const { summary, uncovered, recommendations, diff } = data;

  const covColor = coverageColor(summary.coverage_pct);
  const dupColor = summary.duplicates_found > 0 ? "#f0c060" : "#4a9e6b";
  const untagColor = summary.untagged_cases > 0 ? "#f0c060" : "#4a9e6b";

  return (
    <div style={{ background: "#211d18", border: "1px solid #2a2520", borderRadius: 8, padding: "14px 16px", marginTop: 8 }}>

      {/* Title row */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12 }}>
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" style={{ color: "#f0c060" }}>
          <circle cx="8" cy="8" r="6" /><path d="M5 8l2 2 4-4" />
        </svg>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#f0c060", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Audit Summary
        </span>
        <DiffBadge diff={diff} />
      </div>

      {/* Metrics */}
      <div style={{ display: "flex", gap: 20, marginBottom: 12, flexWrap: "wrap" }}>
        <Metric label="Pokrycie" value={`${summary.coverage_pct}%`} color={covColor} />
        <Metric label="Duplikaty" value={summary.duplicates_found} color={dupColor} />
        <Metric label="Bez tagów" value={summary.untagged_cases} color={untagColor} />
        {summary.requirements_total > 0 && (
          <Metric
            label="Wymagania"
            value={`${summary.requirements_covered}/${summary.requirements_total}`}
          />
        )}
      </div>

      {/* Uncovered requirements */}
      {uncovered.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, color: "#6a5f50", marginBottom: 6 }}>Niepokryte wymagania:</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {uncovered.map((r) => (
              <span
                key={r}
                style={{
                  padding: "2px 7px", borderRadius: 4, fontSize: 10, fontWeight: 700,
                  fontFamily: "monospace", background: "rgba(192,80,74,0.2)",
                  color: "#e08080", border: "1px solid rgba(192,80,74,0.3)",
                }}
              >
                {r}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: sources && sources.length > 0 ? 0 : 0 }}>
          {recommendations.map((rec, i) => (
            <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 7, fontSize: 12, color: "#a09078", lineHeight: 1.4 }}>
              <span style={{ color: "#c8902a", flexShrink: 0, marginTop: 1 }}>→</span>
              <span>{rec}</span>
            </div>
          ))}
        </div>
      )}

      {/* Sources toggle */}
      {sources && sources.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <button
            onClick={() => setSourcesOpen((v) => !v)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              fontSize: 11, color: "#6a5f50", cursor: "pointer",
              padding: "6px 0 0", borderTop: "1px solid #2a2520",
              background: "none", border: "none", borderTop: "1px solid #2a2520",
              width: "100%", textAlign: "left", transition: "color 0.15s",
            }}
            className="hover:text-buddy-text-muted"
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 4h12M2 8h8M2 12h5" />
            </svg>
            {sources.length} {sources.length === 1 ? "źródło RAG" : "źródła RAG"}
            <svg
              width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5"
              style={{ marginLeft: "auto", transition: "transform 0.2s", transform: sourcesOpen ? "rotate(180deg)" : "none" }}
            >
              <path d="M2 4l3 3 3-3" />
            </svg>
          </button>
          {sourcesOpen && (
            <div style={{ paddingTop: 8 }}>
              {sources.map((s, i) => (
                <div
                  key={i}
                  style={{ display: "flex", gap: 6, padding: "5px 8px", borderRadius: 5, background: "#1a1612", marginBottom: 4, fontSize: 11 }}
                >
                  <span style={{ color: "#c8902a", fontWeight: 600, fontFamily: "monospace", flexShrink: 0 }}>{s.filename}</span>
                  <span style={{ color: "#6a5f50" }}>…{s.excerpt}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
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
