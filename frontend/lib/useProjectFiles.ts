"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ProjectFile {
  filename: string;
  file_path: string;
}

export function useProjectFiles(projectId: string) {
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [uploading, setUploading] = useState(false);

  const fetchFiles = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_BASE}/api/files/${encodeURIComponent(projectId)}`
      );
      if (res.ok) {
        const data = await res.json();
        setFiles(data.files ?? data ?? []);
      }
    } catch {
      // Backend offline
    }
  }, [projectId]);

  const uploadFiles = useCallback(
    async (newFiles: File[]): Promise<string[]> => {
      if (!newFiles.length) return [];
      setUploading(true);
      try {
        const formData = new FormData();
        newFiles.forEach((f) => formData.append("files", f));
        const res = await fetch(
          `${API_BASE}/api/files/${encodeURIComponent(projectId)}/upload`,
          { method: "POST", body: formData }
        );
        if (res.ok) {
          const data = await res.json();
          await fetchFiles();
          return data.file_paths ?? data.paths ?? [];
        }
      } catch {
        // ignore
      } finally {
        setUploading(false);
      }
      return [];
    },
    [projectId, fetchFiles]
  );

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  return { files, uploading, uploadFiles, fetchFiles };
}
