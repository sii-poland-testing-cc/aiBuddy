import dagre from "dagre";
import type { MindMapNode as ApiNode, MindMapEdge as ApiEdge } from "../components/MindMap";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface ModalNode {
  id: string;
  label: string;
  type: string;
  x: number;
  y: number;
  depth: number;
  desc?: string;
}

// ── Pure helpers ───────────────────────────────────────────────────────────────

/**
 * Returns true when a node at `depth` should be rendered at the given `zoom` level.
 * Implements the two-tier cluster collapse used by MindMapModal.
 */
export function isNodeVisible(depth: number, zoom: number): boolean {
  if (zoom < 0.30 && depth >= 2) return false;
  if (zoom < 0.55 && depth >= 3) return false;
  return true;
}

// ── dagre layout ──────────────────────────────────────────────────────────────

export function layoutModalNodes(apiNodes: ApiNode[], apiEdges: ApiEdge[]): ModalNode[] {
  if (!apiNodes.length) return [];

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 70, ranksep: 90, marginx: 60, marginy: 60 });

  apiNodes.forEach((n) => g.setNode(n.id, { width: 136, height: 30 }));
  apiEdges.forEach((e) => {
    if (g.hasNode(e.source) && g.hasNode(e.target)) g.setEdge(e.source, e.target);
  });
  dagre.layout(g);

  // BFS depth from root (node with no incoming edges)
  const targetIds = new Set(apiEdges.map((e) => e.target));
  const rootNode = apiNodes.find((n) => !targetIds.has(n.id));
  const depth: Record<string, number> = {};
  if (rootNode) {
    const queue: { id: string; d: number }[] = [{ id: rootNode.id, d: 0 }];
    while (queue.length) {
      const { id, d } = queue.shift()!;
      if (depth[id] !== undefined) continue;
      depth[id] = d;
      apiEdges.filter((e) => e.source === id).forEach((e) => queue.push({ id: e.target, d: d + 1 }));
    }
  }

  return apiNodes.map((n) => {
    const pos = g.node(n.id);
    return {
      id: n.id,
      label: n.label,
      type: n.type,
      x: pos?.x ?? 0,
      y: pos?.y ?? 0,
      depth: depth[n.id] ?? 0,
      desc: n.description,
    };
  });
}
