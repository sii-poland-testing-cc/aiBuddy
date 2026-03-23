"use client";

import { useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AuditPipelineOptions {
  projectId: string;
  extractRequirements: (message?: string) => Promise<void>;
  isExtracting: boolean;
  runMapping: () => Promise<void>;
  isMappingRunning: boolean;
  send: (text: string, filePaths?: string[], opts?: { skipUserMessage?: boolean }) => Promise<void>;
  addUserMessage: (text: string) => void;
  addStatusMessage: (text: string) => void;
  getSelectedFilePaths: () => string[];
}

export function useAuditPipeline({
  projectId,
  extractRequirements,
  isExtracting,
  runMapping,
  isMappingRunning,
  send,
  addUserMessage,
  addStatusMessage,
  getSelectedFilePaths,
}: AuditPipelineOptions) {

  const handleAuditPipeline = useCallback(
    async (userMessage: string, extraPaths: string[] = []) => {
      // Show user message in chat immediately
      addUserMessage(userMessage || "Uruchom audyt");

      try {
        // ── Step 1: Requirements extraction if never done ─────────────────
        let didExtract = false;
        if (!isExtracting) {
          try {
            const statsRes = await fetch(`${API_BASE}/api/requirements/${projectId}/stats`);
            const stats = statsRes.ok ? await statsRes.json() : { has_requirements: false };
            if (!stats.has_requirements) {
              addStatusMessage("Rozpoczynam ekstrakcję wymagań...");
              await extractRequirements();
              didExtract = true;
            }
          } catch {
            // stats fetch failed — skip extraction, proceed to mapping check
          }
        }

        // ── Step 2: Mapping if stale or never run ─────────────────────────
        if (!isMappingRunning) {
          try {
            const stalenessRes = await fetch(`${API_BASE}/api/mapping/${projectId}/staleness`);
            const staleness = stalenessRes.ok ? await stalenessRes.json() : { is_stale: true };
            if (staleness.is_stale) {
              addStatusMessage(
                didExtract
                  ? "Wymagania gotowe. Rozpoczynam mapowanie..."
                  : "Rozpoczynam mapowanie wymagań..."
              );
              await runMapping();
            }
          } catch {
            // staleness fetch failed — proceed to audit anyway
          }
        }

        // ── Step 3: Audit ─────────────────────────────────────────────────
        const paths = [...getSelectedFilePaths(), ...extraPaths];
        await send(userMessage || "Uruchom audyt", paths, { skipUserMessage: true });

      } catch {
        // Individual steps surface errors via their own hooks
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projectId, extractRequirements, isExtracting, runMapping, isMappingRunning,
     send, addUserMessage, addStatusMessage, getSelectedFilePaths]
  );

  return { handleAuditPipeline };
}
