import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import MindMap from "../components/MindMap";

const NODES = [
  { id: "e1", label: "Test Case",   type: "data",    x: 400, y: 200 },
  { id: "e2", label: "QA Engineer", type: "actor",   x: 200, y: 300 },
  { id: "e3", label: "Regression",  type: "process", x: 550, y: 300 },
];

const EDGES = [
  { source: "e2", target: "e1", label: "manages" },
  { source: "e3", target: "e1", label: "executes" },
];

describe("MindMap", () => {
  it("renders without crashing given mock nodes and edges", () => {
    const { container } = render(<MindMap nodes={NODES} edges={EDGES} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
  });

  it("renders one rect per node", () => {
    const { container } = render(<MindMap nodes={NODES} edges={EDGES} />);
    const rects = container.querySelectorAll("rect");
    expect(rects.length).toBe(NODES.length);
  });

  it("renders edge lines between nodes", () => {
    const { container } = render(<MindMap nodes={NODES} edges={EDGES} />);
    const lines = container.querySelectorAll("line");
    expect(lines.length).toBe(EDGES.length);
  });

  it("renders edge labels", () => {
    render(<MindMap nodes={NODES} edges={EDGES} />);
    expect(screen.getByText("manages")).toBeTruthy();
    expect(screen.getByText("executes")).toBeTruthy();
  });

  it("renders node labels", () => {
    render(<MindMap nodes={NODES} edges={EDGES} />);
    expect(screen.getByText("Test Case")).toBeTruthy();
    expect(screen.getByText("QA Engineer")).toBeTruthy();
  });

  it("renders with empty nodes and edges without crashing", () => {
    const { container } = render(<MindMap nodes={[]} edges={[]} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("renders nodes as rects when x/y missing (dagre computes layout)", () => {
    const noCoordNodes = [
      { id: "n1", label: "Alpha", type: "data" },
      { id: "n2", label: "Beta",  type: "actor" },
    ];
    const { container } = render(<MindMap nodes={noCoordNodes} edges={[]} />);
    expect(container.querySelectorAll("rect").length).toBe(2);
  });

  it("includes an arrow marker definition", () => {
    const { container } = render(<MindMap nodes={NODES} edges={EDGES} />);
    const marker = container.querySelector("marker#arrow");
    expect(marker).toBeTruthy();
  });
});
