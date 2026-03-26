/**
 * Shared domain types used across panel components and page-level wiring.
 * Kept here so components can import them without coupling to each other.
 */

export interface PanelFile {
  id: string;
  filename: string;
  file_path: string;
  source_type: "file" | "url" | "jira" | "confluence";
  selected: boolean;
  isNew: boolean; // last_used_in_audit_id === null
}

export interface AuditSnapshot {
  id: string;
  created_at: string;
  summary: {
    coverage_pct: number;
    duplicates_found?: number;
    untagged_cases?: number;
    requirements_total?: number;
    requirements_covered?: number;
  };
  diff: { coverage_delta: number | null; new_covered?: string[]; newly_uncovered?: string[] } | null;
  requirements_uncovered?: string[];
  recommendations?: string[];
  files_used?: string[];
  work_context_id?: string | null;
  lifecycle_status?: string | null;
}
