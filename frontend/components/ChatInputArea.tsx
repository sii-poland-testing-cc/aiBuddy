"use client";

import { useState, useRef, useCallback } from "react";

const ACCEPTED = ".xlsx,.csv,.json,.pdf,.feature,.txt,.md";

function FileChip({
  name,
  onRemove,
}: {
  name: string;
  onRemove: () => void;
}) {
  const ext = name.split(".").pop()?.toUpperCase() ?? "FILE";
  return (
    <div className="inline-flex items-center gap-1.5 bg-buddy-elevated border border-buddy-muted rounded-md px-2 py-0.5 text-xs font-mono text-buddy-gold">
      <span className="opacity-70">{ext}</span>
      <span className="text-buddy-text">{name}</span>
      <button
        onClick={onRemove}
        className="text-buddy-gold leading-none hover:text-buddy-gold-light"
      >
        ×
      </button>
    </div>
  );
}

interface ChatInputAreaProps {
  onSend: (text: string, filePaths?: string[]) => void;
  onStop: () => void;
  isLoading: boolean;
  onUploadFiles: (files: File[]) => Promise<string[]>;
  isUploading?: boolean;
}

export default function ChatInputArea({
  onSend,
  onStop,
  isLoading,
  onUploadFiles,
  isUploading,
}: ChatInputAreaProps) {
  const [text, setText] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(async () => {
    if (isLoading) {
      onStop();
      return;
    }
    if (!text.trim() && attachedFiles.length === 0) return;

    let filePaths: string[] = [];
    if (attachedFiles.length > 0) {
      filePaths = await onUploadFiles(attachedFiles);
    }
    onSend(text, filePaths);
    setText("");
    setAttachedFiles([]);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }, [isLoading, onStop, text, attachedFiles, onUploadFiles, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    setAttachedFiles((prev) => [...prev, ...files]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const canSend = !isUploading && (text.trim().length > 0 || attachedFiles.length > 0);

  return (
    <div className="px-[60px] pb-6 pt-4 bg-buddy-base shrink-0">
      {/* Attached file chips */}
      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2.5">
          {attachedFiles.map((f, i) => (
            <FileChip
              key={i}
              name={f.name}
              onRemove={() =>
                setAttachedFiles((prev) => prev.filter((_, j) => j !== i))
              }
            />
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="flex items-end gap-2.5 bg-buddy-elevated border border-buddy-border-dark rounded-[14px] px-3.5 py-3 shadow-[0_0_0_1px_rgba(200,144,42,0.05)]">
        {/* Attach */}
        <button
          onClick={() => fileInputRef.current?.click()}
          title="Wgraj plik"
          className="w-9 h-9 bg-buddy-border rounded-lg flex items-center justify-center text-base shrink-0 hover:bg-buddy-border-dark transition-colors"
        >
          📎
        </button>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={(e) => {
            const el = e.currentTarget;
            el.style.height = "auto";
            el.style.height = Math.min(el.scrollHeight, 140) + "px";
          }}
          placeholder="Zadaj pytanie, wgraj suite testów, poproś o audyt..."
          rows={1}
          className="flex-1 bg-transparent text-sm text-buddy-text placeholder:text-buddy-text-muted leading-relaxed max-h-[140px] overflow-y-auto pt-2"
        />

        {/* Send / Stop */}
        <button
          onClick={handleSend}
          disabled={!isLoading && !canSend}
          className={`w-9 h-9 rounded-[9px] flex items-center justify-center text-base shrink-0 transition-all ${
            isLoading
              ? "bg-buddy-border text-buddy-gold cursor-wait"
              : canSend
              ? "bg-gradient-to-br from-buddy-gold to-buddy-gold-light text-buddy-surface hover:opacity-90"
              : "bg-buddy-border text-buddy-text-ghost cursor-not-allowed"
          }`}
        >
          {isLoading ? "■" : "↑"}
        </button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ACCEPTED}
        className="hidden"
        onChange={handleFileChange}
      />

      <div className="text-center mt-2 text-[11px] text-buddy-text-ghost">
        Enter — wyślij · Shift+Enter — nowa linia · Obsługuje: .xlsx .csv .pdf
        .json .feature
      </div>
    </div>
  );
}
