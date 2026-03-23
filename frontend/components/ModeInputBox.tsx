"use client";

import { useRef, useEffect, useCallback } from "react";

type Mode = "context" | "requirements" | "audit";

interface AttachedFile {
  name: string;
  ext?: string;
}

interface ModeInputBoxProps {
  activeMode: Mode;
  onModeChange: (mode: Mode) => void;
  lockedModes?: Mode[];
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop?: () => void;
  loading?: boolean;
  attachedFiles?: AttachedFile[];
  onRemoveFile?: (index: number) => void;
  onAttachFiles?: () => void;
}

const MODE_LABELS: Record<Mode, string> = {
  context: "Context Builder",
  requirements: "Requirements",
  audit: "Suite Analyzer",
};

const MODE_PLACEHOLDERS: Record<Mode, string> = {
  context: "Zapytaj o kontekst projektu…",
  requirements: "Zapytaj o wymagania…",
  audit: "Załącz pliki testowe i wpisz polecenie…",
};

const MODES: Mode[] = ["context", "requirements", "audit"];

export default function ModeInputBox({
  activeMode,
  onModeChange,
  lockedModes = [],
  value,
  onChange,
  onSend,
  onStop,
  loading = false,
  attachedFiles = [],
  onRemoveFile,
  onAttachFiles,
}: ModeInputBoxProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
  }, []);

  useEffect(() => {
    resizeTextarea();
  }, [value, resizeTextarea]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!loading && value.trim()) onSend();
    }
  };

  return (
    <div style={{ padding: "8px 48px 16px", flexShrink: 0 }}>

      {/* File chips (above box) */}
      {attachedFiles.length > 0 && (
        <div
          style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}
        >
          {attachedFiles.map((file, i) => {
            const dot = file.name.lastIndexOf(".");
            const ext = file.ext ?? (dot !== -1 ? file.name.slice(dot + 1).toUpperCase() : "");
            const base = dot !== -1 ? file.name.slice(0, dot) : file.name;
            return (
              <span
                key={i}
                data-testid="file-chip"
                className="flex items-center gap-1.5 border border-buddy-border-light bg-buddy-surface2 text-buddy-text-muted"
                style={{ borderRadius: 5, padding: "4px 10px", fontSize: 11 }}
              >
                {ext && (
                  <span
                    className="font-mono font-bold"
                    style={{ fontSize: 10, color: "rgba(200,144,42,0.7)" }}
                  >
                    {ext}
                  </span>
                )}
                <span style={{ maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {base}
                </span>
                <button
                  aria-label={`Remove ${file.name}`}
                  onClick={() => onRemoveFile?.(i)}
                  className="text-buddy-text-dim hover:text-buddy-gold transition-colors"
                  style={{ fontSize: 13, lineHeight: 1, background: "none", border: "none", cursor: "pointer", padding: 0 }}
                >
                  ×
                </button>
              </span>
            );
          })}
        </div>
      )}

      {/* Main box */}
      <div
        className="border border-buddy-border-light bg-buddy-surface focus-within:border-buddy-gold/40"
        style={{ borderRadius: 12, transition: "border-color 0.15s" }}
      >

        {/* Mode row */}
        <div
          className="flex items-center border-b border-buddy-border"
          style={{ padding: "8px 12px 6px", gap: 4 }}
        >
          {MODES.map((mode, idx) => {
            const isActive = activeMode === mode;
            const isLocked = lockedModes.includes(mode);
            return (
              <div key={mode} className="flex items-center" style={{ gap: 4 }}>
                {idx > 0 && (
                  <span
                    className="bg-buddy-border shrink-0"
                    style={{ width: 1, height: 14 }}
                  />
                )}
                <button
                  data-testid={`mode-pill-${mode}`}
                  onClick={() => !isLocked && onModeChange(mode)}
                  disabled={isLocked}
                  aria-pressed={isActive}
                  className={`flex items-center gap-1 font-medium transition-colors ${
                    isActive
                      ? "bg-buddy-gold/15 border-buddy-gold/50 text-buddy-gold-light"
                      : isLocked
                      ? "border-buddy-border text-buddy-text-ghost cursor-not-allowed opacity-50"
                      : "border-buddy-border text-buddy-text-dim hover:text-buddy-text-muted hover:border-buddy-border-dark"
                  }`}
                  style={{
                    height: 24,
                    padding: "0 10px",
                    borderRadius: 20,
                    fontSize: 11,
                    fontWeight: isActive ? 600 : 500,
                    border: "1px solid",
                    background: isActive ? undefined : "transparent",
                  }}
                >
                  {isLocked && (
                    <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                      <rect x="2" y="5" width="8" height="6" rx="1" />
                      <path d="M4 5V4a2 2 0 0 1 4 0v1" />
                    </svg>
                  )}
                  {MODE_LABELS[mode]}
                </button>
              </div>
            );
          })}
        </div>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => { onChange(e.target.value); resizeTextarea(); }}
          onKeyDown={handleKeyDown}
          placeholder={MODE_PLACEHOLDERS[activeMode]}
          rows={1}
          className="w-full bg-transparent text-buddy-text placeholder:text-buddy-text-dim resize-none focus:outline-none"
          style={{
            padding: "10px 14px 6px",
            fontSize: 13,
            minHeight: 44,
            maxHeight: 140,
            lineHeight: 1.5,
            display: "block",
          }}
        />

        {/* Bottom actions */}
        <div
          className="flex items-center justify-end"
          style={{ padding: "4px 10px 8px" }}
        >
          {/* attach + hint + send */}
          <div className="flex items-center gap-2">
            <button
              data-testid="attach-btn"
              onClick={onAttachFiles}
              className="border border-buddy-border text-buddy-text-dim hover:text-buddy-text-muted hover:border-buddy-border-dark transition-colors"
              style={{ padding: "5px 10px", borderRadius: 6, fontSize: 12, background: "none", cursor: "pointer" }}
              aria-label="Attach files"
            >
              +
            </button>

            <span
              className="text-buddy-text-faint select-none"
              style={{ fontSize: 11 }}
            >
              ⏎ wyślij · ⇧⏎ nowa linia
            </span>

            {loading ? (
              <button
                data-testid="stop-btn"
                onClick={onStop}
                className="bg-buddy-elevated border border-buddy-border text-buddy-text-muted hover:text-buddy-text transition-colors font-bold"
                style={{ padding: "5px 14px", borderRadius: 6, fontSize: 12 }}
              >
                ■ Stop
              </button>
            ) : (
              <button
                data-testid="send-btn"
                onClick={onSend}
                disabled={!value.trim()}
                className="bg-buddy-gold text-buddy-surface font-bold hover:bg-buddy-gold-light disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
                style={{ padding: "5px 14px", borderRadius: 6, fontSize: 12 }}
              >
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <path d="M14 8H2M14 8L9 3M14 8L9 13" />
                </svg>
                Wyślij
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
