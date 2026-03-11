"use client";

import { useState } from "react";

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

interface MindMapProps {
  nodes: MindMapNode[];
  edges: MindMapEdge[];
}

export default function MindMap({ nodes, edges }: MindMapProps) {
  const [hovered, setHovered] = useState<string | null>(null);

  // Use x,y from data if present, otherwise fall back to circular layout
  const W = 750, H = 480;
  const CX = W / 2, CY = H / 2;
  const hasCoords = nodes.length > 0 && nodes[0].x != null;

  const positioned = hasCoords
    ? nodes
    : nodes.map((node, i) => {
        const R = Math.min(170, 40 * nodes.length);
        const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
        return { ...node, x: CX + R * Math.cos(angle), y: CY + R * Math.sin(angle) };
      });

  const posMap = Object.fromEntries(positioned.map((n) => [n.id, n]));

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${W} ${H}`}
      style={{ overflow: "visible" }}
    >
      <defs>
        <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#3a3028" />
        </marker>
      </defs>

      {edges.map((e, i) => {
        const src = posMap[e.source];
        const tgt = posMap[e.target];
        if (!src || !tgt) return null;
        const mx = ((src.x ?? 0) + (tgt.x ?? 0)) / 2;
        const my = ((src.y ?? 0) + (tgt.y ?? 0)) / 2;
        return (
          <g key={i}>
            <line
              x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
              stroke="#3a3028" strokeWidth="1.5"
              markerEnd="url(#arrow)"
            />
            {e.label && (
              <text
                x={mx} y={my - 5}
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

      {positioned.map((node) => {
        const color = TYPE_COLORS[node.type] ?? "#c8902a";
        const isH = hovered === node.id;
        const r = isH ? 36 : 30;
        return (
          <g
            key={node.id}
            onMouseEnter={() => setHovered(node.id)}
            onMouseLeave={() => setHovered(null)}
            style={{ cursor: "pointer" }}
          >
            <circle
              cx={node.x} cy={node.y} r={r}
              fill={isH ? color + "33" : color + "18"}
              stroke={color}
              strokeWidth={isH ? 2 : 1.5}
              style={{ transition: "all 0.2s" }}
            />
            <text
              x={node.x} y={(node.y ?? 0) + 4}
              textAnchor="middle"
              fill={color}
              fontSize="11"
              fontFamily="DM Sans, sans-serif"
              fontWeight="600"
            >
              {node.label}
            </text>
            {isH && (
              <text
                x={node.x} y={(node.y ?? 0) + 20}
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
