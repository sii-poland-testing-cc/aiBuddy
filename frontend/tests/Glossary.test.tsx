import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Glossary from "../components/Glossary";

const ITEMS = [
  {
    term: "Test Case",
    definition: "A set of conditions to verify system behaviour.",
    related_terms: ["Test Suite", "Scenario"],
  },
  {
    term: "Defect",
    definition: "A deviation from expected system behaviour.",
    related_terms: ["Bug", "Issue"],
  },
  {
    term: "Coverage",
    definition: "Fraction of requirements exercised by tests.",
    related_terms: [],
  },
];

describe("Glossary", () => {
  it("renders all items when no search query", () => {
    render(<Glossary items={ITEMS} />);
    expect(screen.getByText("Test Case")).toBeTruthy();
    expect(screen.getByText("Defect")).toBeTruthy();
    expect(screen.getByText("Coverage")).toBeTruthy();
  });

  it("renders definitions", () => {
    render(<Glossary items={ITEMS} />);
    expect(screen.getByText("A set of conditions to verify system behaviour.")).toBeTruthy();
  });

  it("renders related_terms as chips", () => {
    render(<Glossary items={ITEMS} />);
    expect(screen.getByText("Test Suite")).toBeTruthy();
    expect(screen.getByText("Bug")).toBeTruthy();
  });

  it("filters items by term on search input", async () => {
    render(<Glossary items={ITEMS} />);
    const input = screen.getByPlaceholderText("Search terms…");
    await userEvent.type(input, "defect");

    expect(screen.getByText("Defect")).toBeTruthy();
    expect(screen.queryByText("Test Case")).toBeNull();
    expect(screen.queryByText("Coverage")).toBeNull();
  });

  it("filters items by definition text", async () => {
    render(<Glossary items={ITEMS} />);
    const input = screen.getByPlaceholderText("Search terms…");
    await userEvent.type(input, "fraction");

    expect(screen.getByText("Coverage")).toBeTruthy();
    expect(screen.queryByText("Defect")).toBeNull();
  });

  it("shows empty state when no results match", async () => {
    render(<Glossary items={ITEMS} />);
    const input = screen.getByPlaceholderText("Search terms…");
    await userEvent.type(input, "xyznotfound");

    expect(screen.getByText("Brak wyników")).toBeTruthy();
  });

  it("renders empty list without crashing", () => {
    render(<Glossary items={[]} />);
    expect(screen.getByPlaceholderText("Search terms…")).toBeTruthy();
  });
});
