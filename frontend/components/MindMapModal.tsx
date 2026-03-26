"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { layoutModalNodes, isNodeVisible } from "../lib/mindMapLayout";
import type { ModalNode } from "../lib/mindMapLayout";

interface ModalEdge {
  source: string;
  target: string;
}

interface Tooltip {
  node: ModalNode;
  x: number;
  y: number;
}

interface MindMapModalProps {
  open: boolean;
  onClose: () => void;
  nodes: ModalNode[];
  edges: ModalEdge[];
  currentContextId?: string | null;
  contexts?: import("../lib/useWorkContext").WorkContext[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const CLUSTER_COLORS: Record<string, string> = {
  payment:   "#4a9e6b",
  auth:      "#5b7fba",
  orders:    "#9b6bbf",
  reporting: "#c8902a",
  notif:     "#ba7a5b",
  root:      "#c8902a",
};

const TYPE_STROKE: Record<string, string> = {
  root:    "#c8902a",
  process: "#4a9e6b",
  actor:   "#5b7fba",
  concept: "#9b6bbf",
  data:    "#ba7a5b",
  system:  "#9b6bbf",
};

const LEGEND = [
  { label: "system/root",  color: "#c8902a" },
  { label: "process",      color: "#4a9e6b" },
  { label: "actor",        color: "#5b7fba" },
  { label: "concept",      color: "#9b6bbf" },
  { label: "data",         color: "#ba7a5b" },
] as const;

// Node dimensions by depth
function nodeDims(depth: number) {
  if (depth === 0) return { w: 150, h: 36, rx: 10 };
  if (depth === 1) return { w: 136, h: 30, rx: 8 };
  if (depth === 2) return { w: 124, h: 26, rx: 6 };
  return { w: 114, h: 22, rx: 6 };
}

function nodeFontSize(depth: number) {
  return [12, 10, 9, 8][Math.min(depth, 3)];
}

// ── Cluster helper ────────────────────────────────────────────────────────────

function getCluster(id: string, edges: ModalEdge[], visited: Set<string> = new Set()): string {
  if (visited.has(id)) return "root"; // cycle detected — bail out
  visited.add(id);
  const anyParent = edges.find((e) => e.target === id);
  if (anyParent) return getCluster(anyParent.source, edges, visited);
  return id; // reached a root (no incoming edge) — use its id as the cluster key
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function MindMapModal({ open, onClose, nodes, edges, currentContextId, contexts }: MindMapModalProps) {
  const [view, setView] = useState({ zoom: 1, pan: { x: 0, y: 0 } });
  const { zoom, pan } = view;
  const [query, setQuery]       = useState("");
  const [tooltip, setTooltip]   = useState<Tooltip | null>(null);
  const [showOverlay, setShowOverlay] = useState(false);

  // Drag state tracked in refs to avoid re-renders during drag
  const dragging      = useRef(false);
  const dragStart     = useRef({ mx: 0, my: 0, px: 0, py: 0 });
  const canvasRef     = useRef<HTMLDivElement>(null);
  const searchRef     = useRef<HTMLInputElement>(null);

  // ── Derived ──────────────────────────────────────────────────────────────────

  const normalizedQuery = query.toLowerCase().trim();

  const visibleNodes = useMemo(
    () => nodes.filter((n) => isNodeVisible(n.depth, zoom)),
    [nodes, zoom],
  );

  const visibleSet = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes]);

  // Count hidden children for each visible parent
  const hiddenCount = useMemo(() => {
    const counts: Record<string, number> = {};
    nodes.forEach((n) => {
      if (visibleSet.has(n.id)) return;
      const parentEdge = edges.find((e) => e.target === n.id);
      if (parentEdge && visibleSet.has(parentEdge.source)) {
        counts[parentEdge.source] = (counts[parentEdge.source] ?? 0) + 1;
      }
    });
    return counts;
  }, [nodes, edges, visibleSet]);

  const matchCount = useMemo(
    () =>
      normalizedQuery
        ? nodes.filter((n) => n.label.toLowerCase().includes(normalizedQuery)).length
        : nodes.length,
    [nodes, normalizedQuery],
  );

  // ── Zoom helpers ──────────────────────────────────────────────────────────────

  const zoomAt = useCallback((delta: number, cx: number, cy: number) => {
    setView((prev) => {
      const next = Math.min(2.5, Math.max(0.15, prev.zoom + delta));
      const scale = next / prev.zoom;
      return {
        zoom: next,
        pan: {
          x: cx - scale * (cx - prev.pan.x),
          y: cy - scale * (cy - prev.pan.y),
        },
      };
    });
  }, []);

  const stepZoom = useCallback(
    (delta: number) => {
      const wrap = canvasRef.current;
      if (!wrap) return;
      zoomAt(delta, wrap.clientWidth / 2, wrap.clientHeight / 2);
    },
    [zoomAt],
  );

  const resetView = useCallback(() => {
    setView({ zoom: 1, pan: { x: 0, y: 0 } });
  }, []);

  const fitView = useCallback(() => {
    const wrap = canvasRef.current;
    if (!wrap || !nodes.length) return;
    const W = wrap.clientWidth;
    const H = wrap.clientHeight;
    const xs = nodes.map((n) => n.x);
    const ys = nodes.map((n) => n.y);
    const minX = Math.min(...xs) - 80;
    const maxX = Math.max(...xs) + 80;
    const minY = Math.min(...ys) - 50;
    const maxY = Math.max(...ys) + 50;
    const scaleX = W / (maxX - minX);
    const scaleY = H / (maxY - minY);
    const newZoom = Math.min(scaleX, scaleY, 1.2);
    setView({
      zoom: newZoom,
      pan: {
        x: W / 2 - newZoom * ((minX + maxX) / 2),
        y: H / 2 - newZoom * ((minY + maxY) / 2),
      },
    });
  }, [nodes]);

  // ── Wheel zoom (non-passive) ──────────────────────────────────────────────────

  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const delta = e.deltaY > 0 ? -0.12 : 0.12;
      zoomAt(delta, e.clientX - rect.left, e.clientY - rect.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt, open]);

  // ── Drag ──────────────────────────────────────────────────────────────────────

  const startDrag = useCallback((mx: number, my: number) => {
    dragging.current = true;
    dragStart.current = { mx, my, px: 0, py: 0 };
    setView((v) => {
      dragStart.current.px = v.pan.x;
      dragStart.current.py = v.pan.y;
      return v;
    });
  }, []);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 0 || e.button === 1) {
      if (e.button === 1) e.preventDefault(); // suppress autoscroll cursor
      startDrag(e.clientX, e.clientY);
    }
  }, [startDrag]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      setView((v) => ({
        ...v,
        pan: {
          x: dragStart.current.px + (e.clientX - dragStart.current.mx),
          y: dragStart.current.py + (e.clientY - dragStart.current.my),
        },
      }));
    };
    const onUp = () => { dragging.current = false; };
    // Prevent middle-click autoscroll (browser default on mousedown button=1)
    const onAuxDown = (e: MouseEvent) => { if (e.button === 1) e.preventDefault(); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("mousedown", onAuxDown);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("mousedown", onAuxDown);
    };
  }, []);

  // ── Keyboard ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // ── Fit on open ───────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!open) {
      setQuery("");
      setTooltip(null);
      setShowOverlay(false);
      return;
    }
    // Wait one frame for DOM to be ready
    requestAnimationFrame(() => fitView());
  }, [open, fitView]);

  // ── Node click handler ────────────────────────────────────────────────────────

  const handleNodeClick = useCallback((node: ModalNode, e: React.MouseEvent) => {
    e.stopPropagation();
    const x = Math.min(e.clientX + 14, window.innerWidth - 290);
    const y = Math.min(e.clientY - 10, window.innerHeight - 140);
    setTooltip((prev) => (prev?.node.id === node.id ? null : { node, x, y }));
  }, []);

  // ── Render ────────────────────────────────────────────────────────────────────

  if (!open) return null;

  const transform = `translate(${pan.x},${pan.y}) scale(${zoom})`;

  return (
    <div
      data-testid="mindmap-modal"
      className="fixed inset-0 bg-buddy-base flex flex-col"
      style={{ zIndex: 500 }}
    >
      {/* ── Toolbar ─────────────────────────────────────────────────────────── */}
      <div
        className="flex-shrink-0 flex items-center gap-2.5 border-b border-buddy-border bg-buddy-surface"
        style={{ height: 48, padding: "0 16px", borderBottom: showOverlay && currentContextId ? "1px solid rgba(200,144,42,0.3)" : undefined }}
      >
        <span className="font-semibold text-buddy-text" style={{ fontSize: 13, marginRight: 4 }}>
          🗺 Mind Map
        </span>

        {/* Search */}
        <div className="relative flex items-center" style={{ flex: 1, maxWidth: 280 }}>
          <svg
            className="absolute text-buddy-text-dim pointer-events-none"
            style={{ left: 9, width: 13, height: 13 }}
            viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
          >
            <circle cx="6.5" cy="6.5" r="4" />
            <path d="M11 11l3 3" />
          </svg>
          <input
            ref={searchRef}
            data-testid="mm-search"
            type="text"
            placeholder="Szukaj węzłów…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full bg-buddy-surface2 border border-buddy-border-light text-buddy-text placeholder:text-buddy-text-dim focus:outline-none focus:border-buddy-gold/50 transition-colors"
            style={{ padding: "6px 10px 6px 28px", borderRadius: 4, fontSize: 12 }}
          />
        </div>

        {/* Match count */}
        <span
          data-testid="mm-match-count"
          className="font-mono"
          style={{
            fontSize: 11,
            color: normalizedQuery
              ? matchCount > 0 ? "#c8902a" : "#e08080"
              : "#6b6055",
            minWidth: 80,
            whiteSpace: "nowrap",
          }}
        >
          {normalizedQuery
            ? `${matchCount} / ${nodes.length} dopasowań`
            : `${nodes.length} węzłów`}
        </span>

        {/* Context overlay controls */}
        {currentContextId && contexts?.find((c) => c.id === currentContextId) && (() => {
          const ctx = contexts.find((c) => c.id === currentContextId)!;
          return (
            <>
              <span style={{ fontSize: 11, padding: "3px 8px", borderRadius: 4, background: "rgba(200,144,42,0.1)", color: "#c8902a", border: "1px solid rgba(200,144,42,0.3)", whiteSpace: "nowrap" }}>
                🏷 {ctx.name}
              </span>
              <button
                onClick={() => setShowOverlay((v) => !v)}
                className={`flex items-center justify-center border transition-all ${showOverlay ? "border-buddy-gold/40 text-buddy-gold bg-buddy-gold/10" : "border-buddy-border text-buddy-text-muted bg-transparent hover:bg-buddy-surface2 hover:border-buddy-border-light hover:text-buddy-text"}`}
                style={{ minWidth: 60, height: 28, borderRadius: 4, fontSize: 11, cursor: "pointer" }}
              >
                {showOverlay ? "Overlay ✦" : "Domain"}
              </button>
            </>
          );
        })()}

        {/* Zoom controls */}
        <div className="flex items-center gap-0.5">
          <ZoomBtn onClick={() => stepZoom(0.25)} title="Zoom in">+</ZoomBtn>
          <span
            data-testid="mm-zoom-level"
            className="font-mono text-buddy-text-dim text-center"
            style={{ fontSize: 11, minWidth: 38 }}
          >
            {Math.round(zoom * 100)}%
          </span>
          <ZoomBtn onClick={() => stepZoom(-0.25)} title="Zoom out">−</ZoomBtn>
          <ZoomBtn onClick={resetView} title="Reset view" style={{ fontSize: 11 }}>⊙</ZoomBtn>
          <ZoomBtn onClick={fitView} title="Fit to screen" style={{ fontSize: 10 }}>⤢</ZoomBtn>
        </div>

        {/* Close */}
        <button
          onClick={onClose}
          className="border border-buddy-border text-buddy-text-muted hover:border-buddy-border-light hover:text-buddy-text hover:bg-buddy-surface2 transition-all ml-auto"
          style={{ padding: "6px 14px", borderRadius: 4, fontSize: 12, cursor: "pointer", background: "transparent" }}
          aria-label="Close mind map"
        >
          ✕ Zamknij
        </button>
      </div>

      {/* ── Canvas ──────────────────────────────────────────────────────────── */}
      <div
        ref={canvasRef}
        data-testid="mm-canvas"
        className="flex-1 overflow-hidden relative"
        style={{ cursor: dragging.current ? "grabbing" : "grab" }}
        onMouseDown={onMouseDown}
        onClick={() => setTooltip(null)}
      >
        <svg
          width="100%"
          height="100%"
          xmlns="http://www.w3.org/2000/svg"
          style={{ display: "block" }}
        >
          <defs>
            <marker id="arr-modal" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <path d="M0,0 L0,6 L6,3 z" fill="#3a342c" />
            </marker>
            {showOverlay && currentContextId && (
              <filter id="ctx-glow">
                <feGaussianBlur stdDeviation="2" result="blur"/>
                <feComposite in="SourceGraphic" in2="blur" operator="over"/>
              </filter>
            )}
          </defs>
          <g transform={transform}>
            {/* Edges */}
            {edges.map((e) => {
              if (!visibleSet.has(e.source) || !visibleSet.has(e.target)) return null;
              const src = nodes.find((n) => n.id === e.source);
              const dst = nodes.find((n) => n.id === e.target);
              if (!src || !dst) return null;
              const cluster = getCluster(e.target, edges);
              const color = CLUSTER_COLORS[cluster] ?? "#3a342c";
              const srcMatch = normalizedQuery && src.label.toLowerCase().includes(normalizedQuery);
              const dstMatch = normalizedQuery && dst.label.toLowerCase().includes(normalizedQuery);
              const isMatch = srcMatch || dstMatch;
              const dx = dst.x - src.x;
              const dy = dst.y - src.y;
              const d = `M${src.x},${src.y} C${src.x},${src.y + dy * 0.45} ${dst.x},${src.y + dy * 0.55} ${dst.x},${dst.y}`;
              return (
                <path
                  key={`${e.source}-${e.target}`}
                  d={d}
                  fill="none"
                  stroke={normalizedQuery ? (isMatch ? color : "#2a2520") : color}
                  strokeWidth={normalizedQuery ? (isMatch ? 1.8 : 0.6) : 1.4}
                  opacity={normalizedQuery ? (isMatch ? 1 : 0.2) : 0.7}
                  markerEnd="url(#arr-modal)"
                />
              );
            })}

            {/* Nodes */}
            {visibleNodes.map((n) => {
              const isMatch = !!normalizedQuery && n.label.toLowerCase().includes(normalizedQuery);
              const isDimmed = !!normalizedQuery && !isMatch;
              const cluster = getCluster(n.id, edges);
              const strokeColor =
                n.depth === 0
                  ? "#c8902a"
                  : CLUSTER_COLORS[cluster] ?? TYPE_STROKE[n.type] ?? "#3a342c";
              const { w, h, rx } = nodeDims(n.depth);
              const x = n.x - w / 2;
              const y = n.y - h / 2;
              const fs = nodeFontSize(n.depth);
              const labelColor =
                n.depth === 0
                  ? "#0f0d0a"
                  : isMatch
                  ? "#f0c060"
                  : n.depth === 1
                  ? strokeColor
                  : "#a09078";
              const hidden = hiddenCount[n.id] ?? 0;

              return (
                <g
                  key={n.id}
                  data-testid={`mm-node-${n.id}`}
                  data-dimmed={isDimmed ? "true" : "false"}
                  style={{ cursor: "pointer", opacity: isDimmed ? 0.15 : 1 }}
                  onClick={(e) => handleNodeClick(n, e)}
                >
                  {/* Glow ring for search match */}
                  {isMatch && (
                    <rect
                      x={x - 3} y={y - 3}
                      width={w + 6} height={h + 6}
                      rx={rx + 2}
                      fill="none"
                      stroke="rgba(240,192,96,0.35)"
                      strokeWidth={4}
                    />
                  )}

                  {/* Node rect */}
                  <rect
                    x={x} y={y}
                    width={w} height={h}
                    rx={rx}
                    fill={n.depth === 0 ? "#c8902a" : "#1a1612"}
                    fillOpacity={n.depth === 0 ? 0.92 : 1}
                    stroke={n.depth === 0 ? "none" : isMatch ? "#f0c060" : strokeColor}
                    strokeWidth={isMatch ? 2.5 : n.depth === 1 ? 1.5 : 1}
                  />

                  {/* Label */}
                  <text
                    x={n.x}
                    y={n.y + fs * 0.38}
                    textAnchor="middle"
                    fontSize={fs}
                    fontFamily="-apple-system,BlinkMacSystemFont,sans-serif"
                    fill={labelColor}
                    fontWeight={n.depth <= 1 ? "600" : "400"}
                  >
                    {n.label}
                  </text>

                  {/* Cluster collapse badge */}
                  {hidden > 0 && (
                    <>
                      <circle
                        cx={x + w - 4}
                        cy={y - 4}
                        r={9}
                        fill={strokeColor}
                      />
                      <text
                        x={x + w - 4}
                        y={y - 4 + 3.5}
                        textAnchor="middle"
                        fontSize={8}
                        fontWeight="700"
                        fontFamily="monospace"
                        fill="#0f0d0a"
                      >
                        +{hidden}
                      </text>
                    </>
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        {/* ── Context overlay banner ───────────────────────────────────────── */}
        {showOverlay && currentContextId && (
          <div className="absolute inset-x-0 top-0 pointer-events-none" style={{
            background: "linear-gradient(180deg, rgba(200,144,42,0.08) 0%, transparent 60px)",
            height: 60,
          }} />
        )}

        {/* ── Legend (bottom-left) ──────────────────────────────────────────── */}
        <div
          className="absolute flex gap-3.5 border border-buddy-border"
          style={{
            bottom: 16, left: 16,
            background: "rgba(15,13,10,0.8)",
            borderRadius: 4,
            padding: "6px 12px",
            backdropFilter: "blur(4px)",
          }}
        >
          {LEGEND.map((l) => (
            <div key={l.label} className="flex items-center gap-1.5 text-buddy-text-dim" style={{ fontSize: 10 }}>
              <div
                style={{
                  width: 8, height: 8, borderRadius: 2, flexShrink: 0,
                  background: l.label === "system/root" ? l.color : "transparent",
                  border: l.label === "system/root" ? "none" : `1.5px solid ${l.color}`,
                }}
              />
              {l.label}
            </div>
          ))}
        </div>

        {/* ── Hint bar (bottom-right) ───────────────────────────────────────── */}
        <div
          className="absolute border border-buddy-border text-buddy-text-faint pointer-events-none"
          style={{
            bottom: 16, right: 16,
            fontSize: 10,
            background: "rgba(15,13,10,0.7)",
            padding: "4px 10px",
            borderRadius: 20,
          }}
        >
          drag to pan · scroll to zoom · click node for details
        </div>
      </div>

      {/* ── Floating tooltip ──────────────────────────────────────────────────── */}
      {tooltip && (
        <div
          data-testid="mm-tooltip"
          className="fixed border border-buddy-border-light bg-buddy-surface pointer-events-none"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            zIndex: 600,
            borderRadius: 6,
            padding: "10px 14px",
            maxWidth: 260,
            boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
          }}
        >
          <div className="font-bold text-buddy-text" style={{ fontSize: 12, marginBottom: 5 }}>
            {tooltip.node.label}
          </div>
          {(() => {
            const cluster = getCluster(tooltip.node.id, edges);
            const color = CLUSTER_COLORS[cluster] ?? "#a09078";
            return (
              <span
                className="inline-block font-mono font-bold uppercase"
                style={{
                  fontSize: 9,
                  padding: "1px 5px",
                  borderRadius: 3,
                  marginBottom: 6,
                  background: color,
                  color: "#0f0d0a",
                }}
              >
                {tooltip.node.type}
              </span>
            );
          })()}
          {currentContextId && (
            <div className="text-buddy-text-dim" style={{ fontSize: 10, marginTop: 4 }}>
              {contexts?.find(c => c.id === currentContextId)?.name ?? "Context overlay"}
            </div>
          )}
          {tooltip.node.desc && (
            <div className="text-buddy-text-muted" style={{ fontSize: 11, lineHeight: 1.5 }}>
              {tooltip.node.desc}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Small helper component ────────────────────────────────────────────────────

function ZoomBtn({
  children,
  onClick,
  title,
  style,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title?: string;
  style?: React.CSSProperties;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="flex items-center justify-center border border-buddy-border text-buddy-text-muted bg-transparent hover:bg-buddy-surface2 hover:border-buddy-border-light hover:text-buddy-text transition-all"
      style={{ width: 28, height: 28, borderRadius: 4, fontSize: 14, cursor: "pointer", ...style }}
    >
      {children}
    </button>
  );
}
