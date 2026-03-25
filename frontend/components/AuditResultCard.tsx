"use client";

import { useState } from "react";
import type { AuditData, ChatSource } from "@/lib/useAIBuddyChat";
import { coverageColor } from "@/lib/coverageColor";

export { coverageColor };

export function generateAuditMarkdown(data: AuditData, sources?: ChatSource[]): string {
  const { summary, uncovered, recommendations, duplicates } = data;
  const now = new Date().toLocaleString("pl-PL");
  let md = `# Raport Audytu — ${now}\n\n`;

  md += `## Podsumowanie\n\n`;
  md += `| Metryka | Wartość |\n|---------|----------|\n`;
  md += `| Pokrycie wymagań | ${summary.coverage_pct}% |\n`;
  md += `| Duplikaty | ${summary.duplicates_found} |\n`;
  md += `| Bez tagów | ${summary.untagged_cases} |\n`;
  if (summary.requirements_total > 0) {
    md += `| Pokryte wymagania | ${summary.requirements_covered}/${summary.requirements_total} |\n`;
  }
  md += "\n";

  if (uncovered.length > 0) {
    md += `## Niepokryte wymagania\n\n`;
    md += `| # | ID wymagania |\n|---|-------------|\n`;
    uncovered.forEach((r, i) => { md += `| ${i + 1} | \`${r}\` |\n`; });
    md += "\n";
  }

  if (duplicates.length > 0) {
    md += `## Duplikaty\n\n`;
    md += `| # | TC A | TC B | Podobieństwo |\n|---|------|------|--------------|\n`;
    duplicates.forEach((d, i) => {
      const sim = typeof d.similarity === "number" ? `${(d.similarity * 100).toFixed(0)}%` : String(d.similarity);
      md += `| ${i + 1} | ${d.tc_a} | ${d.tc_b} | ${sim} |\n`;
    });
    md += "\n";
  }

  if (recommendations.length > 0) {
    md += `## Rekomendacje\n\n`;
    recommendations.forEach((r, i) => { md += `${i + 1}. ${r}\n`; });
    md += "\n";
  }

  if (sources && sources.length > 0) {
    md += `## Źródła RAG\n\n`;
    sources.forEach((s) => { md += `- **${s.filename}**: …${s.excerpt}\n`; });
  }

  return md;
}

export function downloadMarkdown(content: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `audit-${new Date().toISOString().slice(0, 10)}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function Metric({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <div style={{ fontSize: 10, color: "#6a5f50", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, fontFamily: "monospace", color: color ?? "#e8dcc8" }}>{value}</div>
    </div>
  );
}

export function DiffBadge({ diff }: { diff: AuditData["diff"] }) {
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
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 7px", borderRadius: 20, fontSize: 11, fontWeight: 700, fontFamily: "monospace", background: "rgba(192,80,74,0.2)", color: "#c85a3a" }}>
      ▼ {delta.toFixed(1)}%
    </span>
  );
}

function SourcesToggle({ sources }: { sources?: ChatSource[] }) {
  const [open, setOpen] = useState(false);
  if (!sources || sources.length === 0) return null;
  return (
    <div style={{ marginTop: 10 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "flex", alignItems: "center", gap: 6,
          fontSize: 11, color: "#6a5f50", cursor: "pointer",
          padding: "6px 0 0", background: "none", border: "none",
          borderTop: "1px solid #2a2520", width: "100%", textAlign: "left", transition: "color 0.15s",
        }}
      >
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M2 4h12M2 8h8M2 12h5" />
        </svg>
        {sources.length} {sources.length === 1 ? "źródło RAG" : "źródła RAG"}
        <svg
          width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5"
          style={{ marginLeft: "auto", transition: "transform 0.2s", transform: open ? "rotate(180deg)" : "none" }}
        >
          <path d="M2 4l3 3 3-3" />
        </svg>
      </button>
      {open && (
        <div style={{ paddingTop: 8 }}>
          {sources.map((s, i) => (
            <div key={i} style={{ display: "flex", gap: 6, padding: "5px 8px", borderRadius: 5, background: "#1a1612", marginBottom: 4, fontSize: 11 }}>
              <span style={{ color: "#c8902a", fontWeight: 600, fontFamily: "monospace", flexShrink: 0 }}>{s.filename}</span>
              <span style={{ color: "#6a5f50" }}>…{s.excerpt}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const TH_STYLE: React.CSSProperties = {
  padding: "5px 8px", textAlign: "left", fontSize: 10, fontWeight: 600,
  color: "#6a5f50", textTransform: "uppercase", letterSpacing: "0.05em",
  borderBottom: "1px solid #2a2520", whiteSpace: "nowrap",
};
const TD_STYLE: React.CSSProperties = {
  padding: "6px 8px", fontSize: 12, color: "#a09078",
  borderBottom: "1px solid #1e1a16", verticalAlign: "top",
};

function AuditTableView({ data, sources }: { data: AuditData; sources?: ChatSource[] }) {
  const { summary, uncovered, recommendations, duplicates } = data;
  const covColor = coverageColor(summary.coverage_pct);
  const dupColor = summary.duplicates_found > 0 ? "#c8902a" : "#4a9e6b";
  const untagColor = summary.untagged_cases > 0 ? "#c8902a" : "#4a9e6b";

  return (
    <>
      <div style={{ display: "flex", gap: 20, marginBottom: 14, flexWrap: "wrap" }}>
        <Metric label="Pokrycie" value={`${summary.coverage_pct}%`} color={covColor} />
        <Metric label="Duplikaty" value={summary.duplicates_found} color={dupColor} />
        <Metric label="Bez tagów" value={summary.untagged_cases} color={untagColor} />
        {summary.requirements_total > 0 && (
          <Metric label="Wymagania" value={`${summary.requirements_covered}/${summary.requirements_total}`} />
        )}
      </div>

      {uncovered.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: "#6a5f50", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>Niepokryte wymagania</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ ...TH_STYLE, width: 28 }}>#</th>
                <th style={TH_STYLE}>ID</th>
                <th style={{ ...TH_STYLE, textAlign: "center" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {uncovered.map((r, i) => (
                <tr key={r}>
                  <td style={{ ...TD_STYLE, color: "#6a5f50", width: 28 }}>{i + 1}</td>
                  <td style={{ ...TD_STYLE, fontFamily: "monospace", fontWeight: 700, color: "#e08080" }}>{r}</td>
                  <td style={{ ...TD_STYLE, textAlign: "center" }}>🔴</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {duplicates.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: "#6a5f50", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>Duplikaty</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ ...TH_STYLE, width: 28 }}>#</th>
                <th style={TH_STYLE}>TC A</th>
                <th style={TH_STYLE}>TC B</th>
                <th style={{ ...TH_STYLE, textAlign: "right", width: 60 }}>Podobieństwo</th>
              </tr>
            </thead>
            <tbody>
              {duplicates.map((d, i) => {
                const sim = typeof d.similarity === "number" ? `${(d.similarity * 100).toFixed(0)}%` : String(d.similarity);
                return (
                  <tr key={i}>
                    <td style={{ ...TD_STYLE, color: "#6a5f50", width: 28 }}>{i + 1}</td>
                    <td style={{ ...TD_STYLE, fontFamily: "monospace", fontSize: 11 }}>{d.tc_a}</td>
                    <td style={{ ...TD_STYLE, fontFamily: "monospace", fontSize: 11 }}>{d.tc_b}</td>
                    <td style={{ ...TD_STYLE, textAlign: "right", fontFamily: "monospace", color: "#c8902a" }}>{sim}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {recommendations.length > 0 && (
        <div style={{ marginBottom: 4 }}>
          <div style={{ fontSize: 10, color: "#6a5f50", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>Rekomendacje</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ ...TH_STYLE, width: 28 }}>#</th>
                <th style={TH_STYLE}>Opis</th>
              </tr>
            </thead>
            <tbody>
              {recommendations.map((rec, i) => (
                <tr key={i}>
                  <td style={{ ...TD_STYLE, color: "#6a5f50", width: 28 }}>{i + 1}</td>
                  <td style={TD_STYLE}>{rec}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SourcesToggle sources={sources} />
    </>
  );
}

// ── AuditResultCard ───────────────────────────────────────────────────────────

export function AuditResultCard({ data, sources, onClose }: { data: AuditData; sources?: ChatSource[]; onClose?: () => void }) {
  const [view, setView] = useState<"card" | "table">("card");
  const { summary, uncovered, recommendations, diff } = data;

  const covColor = coverageColor(summary.coverage_pct);
  const dupColor = summary.duplicates_found > 0 ? "#c8902a" : "#4a9e6b";
  const untagColor = summary.untagged_cases > 0 ? "#c8902a" : "#4a9e6b";

  const btnBase: React.CSSProperties = {
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    padding: "2px 7px", borderRadius: 4, fontSize: 10, fontWeight: 600,
    cursor: "pointer", border: "1px solid #3a342c", transition: "all 0.15s",
  };

  return (
    <div style={{ background: "#211d18", border: "1px solid #2a2520", borderRadius: 8, padding: "14px 16px", marginTop: onClose ? 0 : 8 }}>

      {/* Title row */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12 }}>
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" style={{ color: "#c8902a" }}>
          <circle cx="8" cy="8" r="6" /><path d="M5 8l2 2 4-4" />
        </svg>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#c8902a", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Audit Summary
        </span>
        <DiffBadge diff={diff} />

        <div style={{ marginLeft: "auto", display: "flex", gap: 4, alignItems: "center" }}>
          <button
            onClick={() => setView("card")}
            style={{ ...btnBase, background: view === "card" ? "rgba(200,144,42,0.18)" : "transparent", color: view === "card" ? "#c8902a" : "#6a5f50", borderColor: view === "card" ? "rgba(200,144,42,0.4)" : "#3a342c" }}
            title="Widok karty"
          >
            ▦
          </button>
          <button
            onClick={() => setView("table")}
            style={{ ...btnBase, background: view === "table" ? "rgba(200,144,42,0.18)" : "transparent", color: view === "table" ? "#c8902a" : "#6a5f50", borderColor: view === "table" ? "rgba(200,144,42,0.4)" : "#3a342c" }}
            title="Widok tabeli"
          >
            ☰
          </button>
          <button
            onClick={() => downloadMarkdown(generateAuditMarkdown(data, sources))}
            style={{ ...btnBase, background: "transparent", color: "#6a5f50", borderColor: "#3a342c", gap: 4 }}
            title="Pobierz audit.md"
          >
            ↓ .md
          </button>
          {onClose && (
            <button
              onClick={onClose}
              style={{ ...btnBase, background: "transparent", color: "#6a5f50", borderColor: "#3a342c", fontSize: 14, padding: "1px 6px" }}
              title="Zamknij"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {view === "table" ? (
        <AuditTableView data={data} sources={sources} />
      ) : (
        <>
          <div style={{ display: "flex", gap: 20, marginBottom: 12, flexWrap: "wrap" }}>
            <Metric label="Pokrycie" value={`${summary.coverage_pct}%`} color={covColor} />
            <Metric label="Duplikaty" value={summary.duplicates_found} color={dupColor} />
            <Metric label="Bez tagów" value={summary.untagged_cases} color={untagColor} />
            {summary.requirements_total > 0 && (
              <Metric label="Wymagania" value={`${summary.requirements_covered}/${summary.requirements_total}`} />
            )}
          </div>

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

          {recommendations.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {recommendations.map((rec, i) => (
                <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 7, fontSize: 12, color: "#a09078", lineHeight: 1.4 }}>
                  <span style={{ color: "#c8902a", flexShrink: 0, marginTop: 1 }}>→</span>
                  <span>{rec}</span>
                </div>
              ))}
            </div>
          )}

          <SourcesToggle sources={sources} />
        </>
      )}
    </div>
  );
}
