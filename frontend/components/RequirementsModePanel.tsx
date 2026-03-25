"use client";

import type { HeatmapRow } from "../lib/useHeatmap";
import type { PanelFile } from "../lib/types";
import { PanelCard } from "./PanelCard";
import { SourcesCard } from "./SourcesCard";

export interface RequirementsModePanelProps {
  auditFiles?: PanelFile[];
  onAddFiles?: () => void;
  onFileToggle?: (filePath: string, checked: boolean) => void;
  heatmapData?: HeatmapRow[];
}

function heatmapEmoji(color: HeatmapRow["color"]) {
  return { green: "🟢", yellow: "🟡", orange: "🟠", red: "🔴" }[color];
}

export function RequirementsModePanel({
  auditFiles = [],
  onAddFiles,
  onFileToggle,
  heatmapData = [],
}: RequirementsModePanelProps) {
  return (
    <div data-testid="panel-mode-requirements" className="flex flex-col" style={{ gap: 6 }}>
      <SourcesCard
        cardId="sources-requirements"
        auditFiles={auditFiles}
        onAddFiles={onAddFiles}
        onFileToggle={onFileToggle}
      />

      <PanelCard id="heatmap" icon="🗂" title="Heatmap pokrycia" defaultOpen>
        {heatmapData.length > 0 ? (
          <table style={{ width: "100%", tableLayout: "fixed", borderCollapse: "collapse", fontSize: 11 }}>
            <colgroup>
              <col style={{ width: "auto" }} />
              <col style={{ width: 36 }} />
              <col style={{ width: 36 }} />
              <col style={{ width: 40 }} />
              <col style={{ width: 32 }} />
            </colgroup>
            <thead>
              <tr>
                <th className="text-buddy-text-faint font-medium border-b border-buddy-border" style={{ padding: "5px 8px", textAlign: "left", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>Moduł</th>
                <th className="text-buddy-text-faint font-medium border-b border-buddy-border" style={{ padding: "5px 8px", textAlign: "right" }}>Wym.</th>
                <th className="text-buddy-text-faint font-medium border-b border-buddy-border" style={{ padding: "5px 8px", textAlign: "right" }}>Pokr.</th>
                <th className="text-buddy-text-faint font-medium border-b border-buddy-border" style={{ padding: "5px 8px", textAlign: "right" }}>Śr.</th>
                <th className="text-buddy-text-faint font-medium border-b border-buddy-border" style={{ padding: "5px 8px", textAlign: "center" }}>St.</th>
              </tr>
            </thead>
            <tbody>
              {heatmapData.map((row) => (
                <tr key={row.module} className="hover:bg-white/[0.02] transition-colors">
                  <td className="text-buddy-text font-medium font-mono border-b border-buddy-border" style={{ padding: "6px 8px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.module}</td>
                  <td className="text-buddy-text-muted border-b border-buddy-border" style={{ padding: "6px 8px", textAlign: "right" }}>{row.total_requirements}</td>
                  <td className="text-buddy-text-muted border-b border-buddy-border" style={{ padding: "6px 8px", textAlign: "right" }}>{row.covered}</td>
                  <td className="font-mono text-buddy-text-muted border-b border-buddy-border" style={{ padding: "6px 8px", textAlign: "right" }}>{row.avg_score.toFixed(1)}</td>
                  <td className="border-b border-buddy-border" style={{ padding: "6px 8px", textAlign: "center" }}>{heatmapEmoji(row.color)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-buddy-text-faint" style={{ fontSize: 11, textAlign: "center", padding: "8px 0" }}>
            Brak danych heatmapy. Uruchom mapowanie w trybie Audyt.
          </p>
        )}
      </PanelCard>
    </div>
  );
}
