"use client";

import { useState, useMemo } from "react";
import dagre from "dagre";

export interface MindMapNode {
  id: string;
  label: string;
  type: string;
  x?: number;
  y?: number;
  description?: string;
}

export interface MindMapEdge {
  source: string;
  target: string;
  label?: string;
}

const TYPE_COLORS: Record<string, string> = {
  data:    "#c8902a",
  actor:   "#4a9e6b",
  process: "#5b7fba",
  system:  "#9b6bbf",
  concept: "#ba7a5b",
};

const NODE_W = 120;
const NODE_H = 40;

function computeLayout(
  nodes: MindMapNode[],
  edges: MindMapEdge[],
): { positions: Map<string, { x: number; y: number }>; width: number; height: number } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 50, ranksep: 80, marginx: 40, marginy: 40 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => {
    if (g.hasNode(e.source) && g.hasNode(e.target))
      g.setEdge(e.source, e.target);
  });
  dagre.layout(g);
  const positions = new Map<string, { x: number; y: number }>();
  nodes.forEach((n) => {
    const pos = g.node(n.id);
    if (pos) positions.set(n.id, { x: pos.x, y: pos.y });
  });
  const graph = g.graph();
  return { positions, width: graph.width ?? 750, height: graph.height ?? 480 };
}

interface MindMapProps {
  nodes: MindMapNode[];
  edges: MindMapEdge[];
}

export default function MindMap({ nodes, edges }: MindMapProps) {
  const [hovered, setHovered] = useState<string | null>(null);

  const { positions, width, height } = useMemo(
    () => computeLayout(nodes, edges),
    [nodes, edges],
  );

  const viewW = width + 80;
  const viewH = height + 80;

  const posMap = Object.fromEntries(
    nodes.map((n) => [n.id, positions.get(n.id) ?? { x: viewW / 2, y: viewH / 2 }]),
  );

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${viewW} ${viewH}`}
      style={{ overflow: "visible" }}
    >
      <defs>
        <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto-start-reverse">
          <path d="M0,0 L6,3 L0,6 Z" fill="#3a3028" />
        </marker>
      </defs>

      {edges.map((e, i) => {
        const src = posMap[e.source];
        const tgt = posMap[e.target];
        if (!src || !tgt) return null;
        const srcX = src.x, srcY = src.y + 20;
        const tgtX = tgt.x, tgtY = tgt.y - 20;
        const midY = (srcY + tgtY) / 2;
        const d = `M ${srcX},${srcY} C ${srcX},${midY} ${tgtX},${midY} ${tgtX},${tgtY}`;
        return (
          <g key={i}>
            <path
              d={d}
              stroke="#3a3028" strokeWidth="1.5" fill="none"
              markerEnd="url(#arrow)"
            />
            {e.label && (
              <text
                x={(srcX + tgtX) / 2} y={(srcY + tgtY) / 2 - 6}
                textAnchor="middle"
                fill="#5a4e42"
                fontSize="10"
                fontFamily="DM Mono, monospace"
              >
                {e.label}
              </text>
            )}
          </g>
        );
      })}

      {nodes.map((node) => {
        const { x, y } = posMap[node.id];
        const color = TYPE_COLORS[node.type] ?? "#c8902a";
        const isH = hovered === node.id;
        return (
          <g
            key={node.id}
            onMouseEnter={() => setHovered(node.id)}
            onMouseLeave={() => setHovered(null)}
            style={{ cursor: "pointer" }}
          >
            <rect
              x={x - 60} y={y - 20}
              width={NODE_W} height={NODE_H}
              rx={8}
              fill={color + "22"}
              stroke={color}
              strokeWidth={isH ? 2.5 : 1.5}
              style={{ transition: "all 0.2s" }}
            />
            <text
              x={x} y={y + 4}
              textAnchor="middle"
              fill={color}
              fontSize="11"
              fontFamily="DM Mono, monospace"
              fontWeight="600"
            >
              {node.label}
            </text>
            {isH && (
              <text
                x={x} y={y + 28}
                textAnchor="middle"
                fill="#8a7a68"
                fontSize="9"
                fontFamily="monospace"
              >
                {node.type}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
