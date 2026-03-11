"use client";

import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

interface SnapshotDiff {
  coverage_delta: number;
  duplicates_delta: number;
  new_covered: string[];
  newly_uncovered: string[];
  files_added: string[];
  files_removed: string[];
}

interface Snapshot {
  id: string;
  created_at: string;
  files_used: string[];
  summary: {
    coverage_pct: number;
    duplicates_found: number;
    requirements_total: number;
    requirements_covered: number;
  };
  requirements_uncovered: string[];
  recommendations: string[];
  diff: SnapshotDiff | null;
}

interface TrendData {
  labels: string[];
  coverage: number[];
  duplicates: number[];
}

interface AuditHistoryProps {
  projectId: string;
  latestSnapshotId?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  const d = new Date(iso);
  const day = d.getDate();
  const month = d.toLocaleString("pl-PL", { month: "short" });
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${day} ${month} ${hh}:${mm}`;
}

function coverageColor(pct: number): string {
  if (pct >= 80) return "#4a9e6b";
  if (pct >= 50) return "#c8902a";
  return "#c85a3a";
}

function DiffBadge({ delta }: { delta: number }) {
  if (delta > 0)
    return (
      <span style={{ color: "#4a9e6b", fontSize: 11, whiteSpace: "nowrap" }}>
        ▲ +{delta.toFixed(1)}%
      </span>
    );
  if (delta < 0)
    return (
      <span style={{ color: "#c85a3a", fontSize: 11, whiteSpace: "nowrap" }}>
        ▼ {delta.toFixed(1)}%
      </span>
    );
  return (
    <span style={{ color: "#5a4e42", fontSize: 11, whiteSpace: "nowrap" }}>
      → 0%
    </span>
  );
}

function Chip({ label, color = "#c8b89a" }: { label: string; color?: string }) {
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: 10,
        fontFamily: "monospace",
        color,
        background: "#2a2520",
        borderRadius: 3,
        padding: "1px 5px",
        margin: "1px 2px",
      }}
    >
      {label}
    </span>
  );
}

// ── SnapshotRow ───────────────────────────────────────────────────────────────

function SnapshotRow({
  snap,
  isLatest,
  onDelete,
}: {
  snap: Snapshot;
  isLatest: boolean;
  onDelete: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [hovered, setHovered] = useState(false);
  const pct = snap.summary?.coverage_pct ?? 0;
  const dups = snap.summary?.duplicates_found ?? 0;
  const filenames = snap.files_used.map((p) => p.split("/").pop() ?? p);

  const handleDelete = () => {
    if (window.confirm("Usunąć ten snapshot audytu?")) {
      onDelete(snap.id);
    }
  };

  return (
    <div
      style={{
        borderLeft: isLatest ? "3px solid #c8902a" : "3px solid transparent",
        padding: "6px 10px 6px 12px",
        borderBottom: "1px solid #2a2520",
        position: "relative",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      data-testid="snapshot-row"
    >
      {/* Main row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {/* Date */}
        <span style={{ fontSize: 12, color: "#c8b89a", minWidth: 90 }}>
          {formatDate(snap.created_at)}
        </span>

        {/* Coverage badge */}
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: coverageColor(pct),
            minWidth: 38,
          }}
          data-testid="coverage-badge"
          data-coverage={pct}
        >
          {pct.toFixed(0)}%
        </span>

        {/* Diff badge */}
        {snap.diff && <DiffBadge delta={snap.diff.coverage_delta} />}

        {/* Duplicates */}
        <span style={{ fontSize: 11, color: "#5a4e42", minWidth: 70 }}>
          {dups} duplikaty
        </span>

        {/* Files */}
        <span
          style={{
            fontSize: 11,
            color: "#5a4e42",
            flex: 1,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {filenames.join(", ")}
        </span>

        {/* Delete button */}
        {hovered && (
          <button
            onClick={handleDelete}
            title="Usuń snapshot"
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 13,
              color: "#c85a3a",
              padding: "0 2px",
              lineHeight: 1,
            }}
          >
            🗑
          </button>
        )}

        {/* Expand chevron */}
        <button
          onClick={() => setExpanded((e) => !e)}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            fontSize: 11,
            color: "#5a4e42",
            padding: "0 2px",
            lineHeight: 1,
          }}
        >
          {expanded ? "▲" : "▼"}
        </button>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div style={{ marginTop: 8, paddingLeft: 4 }}>
          {snap.requirements_uncovered.length > 0 && (
            <div style={{ marginBottom: 6 }}>
              <span style={{ fontSize: 10, color: "#5a4e42", marginRight: 4 }}>
                Brak pokrycia:
              </span>
              {snap.requirements_uncovered.map((r) => (
                <Chip key={r} label={r} color="#c85a3a" />
              ))}
            </div>
          )}

          {snap.recommendations.length > 0 && (
            <div style={{ marginBottom: 6 }}>
              {snap.recommendations.map((rec, i) => (
                <div
                  key={i}
                  style={{ fontSize: 11, color: "#c8b89a", marginBottom: 2 }}
                >
                  {i + 1}. {rec}
                </div>
              ))}
            </div>
          )}

          {snap.diff && (
            <div style={{ fontSize: 11, color: "#5a4e42" }}>
              {snap.diff.new_covered.length > 0 && (
                <div>
                  <span style={{ color: "#4a9e6b" }}>+ Nowo pokryte: </span>
                  {snap.diff.new_covered.join(", ")}
                </div>
              )}
              {snap.diff.newly_uncovered.length > 0 && (
                <div>
                  <span style={{ color: "#c85a3a" }}>− Utracone: </span>
                  {snap.diff.newly_uncovered.join(", ")}
                </div>
              )}
              {snap.diff.files_added.length > 0 && (
                <div>Dodane pliki: {snap.diff.files_added.join(", ")}</div>
              )}
              {snap.diff.files_removed.length > 0 && (
                <div>Usunięte pliki: {snap.diff.files_removed.join(", ")}</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function AuditHistory({
  projectId,
  latestSnapshotId,
}: AuditHistoryProps) {
  const [open, setOpen] = useState(false);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [trend, setTrend] = useState<TrendData | null>(null);

  const fetchData = () => {
    fetch(`${API_BASE}/api/snapshots/${projectId}`)
      .then((r) => r.json())
      .then((data: Snapshot[]) => setSnapshots(data))
      .catch(() => {});

    fetch(`${API_BASE}/api/snapshots/${projectId}/trend`)
      .then((r) => r.json())
      .then((data: TrendData) => setTrend(data))
      .catch(() => {});
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, latestSnapshotId]);

  const handleDelete = async (id: string) => {
    await fetch(`${API_BASE}/api/snapshots/${projectId}/${id}`, {
      method: "DELETE",
    }).catch(() => {});
    fetchData();
  };

  const trendPoints =
    trend && trend.labels.length >= 2
      ? trend.labels.map((label, i) => ({
          label: formatDate(label),
          coverage: trend.coverage[i],
          duplicates: trend.duplicates[i],
        }))
      : null;

  return (
    <div
      style={{
        margin: "0 60px 8px",
        background: "#1e1a16",
        border: "1px solid #2a2520",
        borderRadius: 8,
        overflow: "hidden",
      }}
    >
      {/* Header / toggle */}
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "7px 12px",
          background: "none",
          border: "none",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span style={{ fontSize: 12, color: "#c8b89a" }}>📋 Historia audytów</span>
        {snapshots.length > 0 && (
          <span
            style={{
              fontSize: 10,
              color: "#5a4e42",
              background: "#2a2520",
              borderRadius: 10,
              padding: "1px 6px",
            }}
          >
            {snapshots.length}
          </span>
        )}
        <span style={{ marginLeft: "auto", fontSize: 10, color: "#5a4e42" }}>
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div style={{ borderTop: "1px solid #2a2520" }}>
          {snapshots.length === 0 ? (
            <div
              style={{ padding: "10px 12px", fontSize: 11, color: "#5a4e42" }}
            >
              Brak zapisanych audytów.
            </div>
          ) : (
            snapshots.map((snap) => (
              <SnapshotRow
                key={snap.id}
                snap={snap}
                isLatest={snap.id === latestSnapshotId}
                onDelete={handleDelete}
              />
            ))
          )}

          {trendPoints && (
            <div
              style={{ padding: "12px 12px 8px", background: "#1e1a16" }}
              data-testid="trend-chart"
            >
              <div
                style={{
                  fontSize: 10,
                  color: "#5a4e42",
                  marginBottom: 6,
                  fontVariant: "small-caps",
                }}
              >
                Trend pokrycia
              </div>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={trendPoints}>
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 9, fill: "#5a4e42" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    yAxisId="left"
                    domain={[0, 100]}
                    tick={{ fontSize: 9, fill: "#5a4e42" }}
                    axisLine={false}
                    tickLine={false}
                    width={28}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tick={{ fontSize: 9, fill: "#5a4e42" }}
                    axisLine={false}
                    tickLine={false}
                    width={24}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#2a2520",
                      border: "1px solid #3a3020",
                      borderRadius: 4,
                      fontSize: 11,
                      color: "#c8b89a",
                    }}
                  />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="coverage"
                    stroke="#c8902a"
                    strokeWidth={2}
                    dot={false}
                    name="Coverage %"
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="duplicates"
                    stroke="#5b7fba"
                    strokeWidth={2}
                    dot={false}
                    name="Duplikaty"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
