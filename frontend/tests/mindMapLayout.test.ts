import { describe, it, expect } from "vitest";
import { isNodeVisible, layoutModalNodes } from "../lib/mindMapLayout";

// ── isNodeVisible ──────────────────────────────────────────────────────────────

describe("isNodeVisible", () => {
  // depth 0 (root) always visible
  it("root node is visible at any zoom", () => {
    expect(isNodeVisible(0, 0.10)).toBe(true);
    expect(isNodeVisible(0, 0.29)).toBe(true);
    expect(isNodeVisible(0, 0.55)).toBe(true);
    expect(isNodeVisible(0, 1.00)).toBe(true);
  });

  // depth 1 always visible
  it("depth-1 node is visible at any zoom", () => {
    expect(isNodeVisible(1, 0.10)).toBe(true);
    expect(isNodeVisible(1, 0.29)).toBe(true);
    expect(isNodeVisible(1, 2.50)).toBe(true);
  });

  // depth 2 — threshold at zoom < 0.30
  it("depth-2 node hidden below zoom 0.30", () => {
    expect(isNodeVisible(2, 0.29)).toBe(false);
    expect(isNodeVisible(2, 0.10)).toBe(false);
  });

  it("depth-2 node visible at zoom >= 0.30", () => {
    expect(isNodeVisible(2, 0.30)).toBe(true);
    expect(isNodeVisible(2, 0.55)).toBe(true);
    expect(isNodeVisible(2, 1.00)).toBe(true);
  });

  // depth 3 — threshold at zoom < 0.55
  it("depth-3 node hidden below zoom 0.55", () => {
    expect(isNodeVisible(3, 0.54)).toBe(false);
    expect(isNodeVisible(3, 0.30)).toBe(false);
    expect(isNodeVisible(3, 0.29)).toBe(false);
  });

  it("depth-3 node visible at zoom >= 0.55", () => {
    expect(isNodeVisible(3, 0.55)).toBe(true);
    expect(isNodeVisible(3, 1.00)).toBe(true);
  });

  // depth 4+ follows depth-3 rule (>= 3 check)
  it("depth-4+ nodes follow the depth>=3 threshold", () => {
    expect(isNodeVisible(4, 0.54)).toBe(false);
    expect(isNodeVisible(4, 0.55)).toBe(true);
    expect(isNodeVisible(10, 0.54)).toBe(false);
    expect(isNodeVisible(10, 0.55)).toBe(true);
  });

  // boundary: exactly at both thresholds simultaneously (zoom 0.29, depth 3)
  it("applies the stricter depth-2 rule first when zoom < 0.30", () => {
    // At zoom=0.29: depth>=2 hidden AND depth>=3 hidden; depth-2 should be false
    expect(isNodeVisible(2, 0.29)).toBe(false);
    expect(isNodeVisible(3, 0.29)).toBe(false);
  });
});

// ── layoutModalNodes ──────────────────────────────────────────────────────────

describe("layoutModalNodes", () => {
  const API_NODES = [
    { id: "root",   label: "Root",    type: "root",    description: "r" },
    { id: "child1", label: "Child 1", type: "process", description: "c1" },
    { id: "child2", label: "Child 2", type: "actor",   description: "c2" },
  ];
  const API_EDGES = [
    { source: "root", target: "child1" },
    { source: "root", target: "child2" },
  ];

  it("returns empty array for no input", () => {
    expect(layoutModalNodes([], [])).toEqual([]);
  });

  it("assigns numeric x,y from dagre layout", () => {
    const result = layoutModalNodes(API_NODES, API_EDGES);
    expect(result.every((n) => typeof n.x === "number" && typeof n.y === "number")).toBe(true);
  });

  it("assigns depth 0 to root, depth 1 to children", () => {
    const result = layoutModalNodes(API_NODES, API_EDGES);
    const byId = Object.fromEntries(result.map((n) => [n.id, n]));
    expect(byId["root"].depth).toBe(0);
    expect(byId["child1"].depth).toBe(1);
    expect(byId["child2"].depth).toBe(1);
  });

  it("maps description to desc field", () => {
    const result = layoutModalNodes(API_NODES, API_EDGES);
    const root = result.find((n) => n.id === "root")!;
    expect(root.desc).toBe("r");
  });

  it("handles disconnected graph (no edges) without crash", () => {
    const result = layoutModalNodes(API_NODES, []);
    expect(result).toHaveLength(3);
    // all nodes get depth 0 when there's no root edge to BFS from
    result.forEach((n) => expect(typeof n.depth).toBe("number"));
  });
});
