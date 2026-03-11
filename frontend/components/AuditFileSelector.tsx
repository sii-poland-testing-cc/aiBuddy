"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SOURCE_ICONS: Record<string, string> = {
  file: "📄",
  url: "🔗",
  jira: "🐛",
  confluence: "📘",
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  const day = d.getDate();
  const month = d.toLocaleString("pl-PL", { month: "short" });
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${day} ${month} ${hh}:${mm}`;
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

export interface FileSelectionItem {
  id: string;
  filename: string;
  file_path: string;
  source_type: string;
  size_bytes: number;
  uploaded_at: string;
  last_used_in_audit_id: string | null;
  last_used_in_audit_at: string | null;
  selected: boolean;
}

interface AuditFileSelectorProps {
  projectId: string;
  onSelectionChange: (selectedPaths: string[]) => void;
  refreshKey?: number;
}

export default function AuditFileSelector({
  projectId,
  onSelectionChange,
  refreshKey = 0,
}: AuditFileSelectorProps) {
  const [items, setItems] = useState<FileSelectionItem[]>([]);
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetch(`${API_BASE}/api/files/${projectId}/audit-selection`)
      .then((r) => r.json())
      .then((data: FileSelectionItem[]) => {
        setItems(data);
        const initial: Record<string, boolean> = {};
        for (const f of data) {
          initial[f.file_path] = f.selected;
        }
        setChecked(initial);
        onSelectionChange(
          data.filter((f) => f.selected).map((f) => f.file_path)
        );
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, refreshKey]);

  const handleChange = (filePath: string, isNonFile: boolean) => {
    if (isNonFile) return;
    setChecked((prev) => {
      const next = { ...prev, [filePath]: !prev[filePath] };
      onSelectionChange(
        items.filter((f) => next[f.file_path]).map((f) => f.file_path)
      );
      return next;
    });
  };

  if (items.length === 0) {
    return (
      <div
        style={{
          margin: "0 60px 8px",
          padding: "10px 16px",
          fontSize: 12,
          color: "#5a4e42",
        }}
      >
        Brak plików — wgraj pliki testowe aby rozpocząć audyt
      </div>
    );
  }

  const newFiles = items.filter((f) => f.selected);
  const usedFiles = items.filter((f) => !f.selected);

  const renderRow = (f: FileSelectionItem) => {
    const isNonFile = f.source_type !== "file";
    const isChecked = !!checked[f.file_path];
    return (
      <div
        key={f.id}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "5px 12px",
          opacity: isChecked ? 1 : 0.5,
        }}
      >
        <input
          type="checkbox"
          checked={isChecked}
          disabled={isNonFile}
          title={isNonFile ? "Źródła URL są zawsze dołączane" : undefined}
          onChange={() => handleChange(f.file_path, isNonFile)}
          style={{
            accentColor: "#c8902a",
            cursor: isNonFile ? "not-allowed" : "pointer",
          }}
        />
        <span>{SOURCE_ICONS[f.source_type] ?? "📄"}</span>
        <span
          style={{
            fontSize: 13,
            color: "#c8b89a",
            flex: 1,
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {truncate(f.filename, 32)}
        </span>
        <span
          style={{
            fontSize: 10,
            fontFamily: "monospace",
            color: "#5a4e42",
            background: "#2a2520",
            borderRadius: 3,
            padding: "1px 5px",
          }}
        >
          {f.source_type}
        </span>
        {f.last_used_in_audit_at && (
          <span style={{ fontSize: 10, color: "#5a4e42", whiteSpace: "nowrap" }}>
            użyty: {formatDate(f.last_used_in_audit_at)}
          </span>
        )}
      </div>
    );
  };

  return (
    <div
      style={{
        background: "#1e1a16",
        border: "1px solid #2a2520",
        borderRadius: 8,
        margin: "0 60px 8px",
        overflow: "hidden",
      }}
    >
      {newFiles.length > 0 && (
        <div>
          <div
            style={{
              fontSize: 11,
              color: "#5a4e42",
              fontVariant: "small-caps",
              padding: "6px 12px 2px",
            }}
          >
            Nowe źródła
          </div>
          {newFiles.map(renderRow)}
        </div>
      )}
      {usedFiles.length > 0 && (
        <div>
          <div
            style={{
              fontSize: 11,
              color: "#5a4e42",
              fontVariant: "small-caps",
              padding: "6px 12px 2px",
            }}
          >
            Poprzednio użyte
          </div>
          {usedFiles.map(renderRow)}
        </div>
      )}
    </div>
  );
}
