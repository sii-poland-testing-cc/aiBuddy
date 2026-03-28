import { useState, useEffect, useCallback } from "react";
import type { PanelFile } from "./types";
import { apiFetch } from "@/lib/apiFetch";

export function usePanelFiles(
  projectId: string,
  refreshKey: number
): [PanelFile[], (filePath: string, checked: boolean) => void] {
  const [panelFiles, setPanelFiles] = useState<PanelFile[]>([]);

  useEffect(() => {
    apiFetch(`/api/files/${projectId}/audit-selection`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data: any[]) => {
        setPanelFiles(
          data.map((f) => ({
            id: f.id,
            filename: f.filename,
            file_path: f.file_path,
            source_type: f.source_type as PanelFile["source_type"],
            selected: f.selected,
            isNew: f.last_used_in_audit_id === null,
          }))
        );
      })
      .catch(() => {});
  }, [projectId, refreshKey]);

  const handleFileToggle = useCallback((filePath: string, checked: boolean) => {
    setPanelFiles((prev) =>
      prev.map((f) => (f.file_path === filePath ? { ...f, selected: checked } : f))
    );
  }, []);

  return [panelFiles, handleFileToggle];
}
