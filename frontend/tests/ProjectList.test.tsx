import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectList from "../components/ProjectList";

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const PROJECTS = [
  { project_id: "p1", name: "PayFlow QA Suite", created_at: "2026-03-01T00:00:00Z" },
  { project_id: "p2", name: "Auth Service v2",  created_at: "2026-03-10T00:00:00Z" },
];

const formatDate = (iso?: string) =>
  iso ? new Date(iso).toLocaleDateString("pl-PL", { day: "numeric", month: "short", year: "numeric" }) : "";

function renderList(overrides: Partial<Parameters<typeof ProjectList>[0]> = {}) {
  return render(
    <ProjectList
      projects={PROJECTS}
      runningProjects={new Set()}
      statuses={{ p1: true, p2: false }}
      formatDate={formatDate}
      {...overrides}
    />
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ProjectList", () => {
  afterEach(() => vi.clearAllMocks());

  it("renders all project names", () => {
    renderList();
    expect(screen.getByText("PayFlow QA Suite")).toBeInTheDocument();
    expect(screen.getByText("Auth Service v2")).toBeInTheDocument();
  });

  it("renders formatted dates", () => {
    renderList();
    expect(screen.getByText(formatDate("2026-03-01T00:00:00Z"))).toBeInTheDocument();
  });

  it("shows empty state when no projects", () => {
    renderList({ projects: [] });
    expect(screen.getByText(/Brak projektów/)).toBeInTheDocument();
  });

  it("clicking a project navigates to /chat/{id}", async () => {
    renderList();
    await userEvent.click(screen.getByText("PayFlow QA Suite"));
    expect(mockPush).toHaveBeenCalledWith("/chat/p1");
  });

  it("each project row has a settings gear button", () => {
    renderList();
    const gearButtons = screen.getAllByTitle("Ustawienia projektu");
    expect(gearButtons).toHaveLength(2);
  });

  it("clicking the gear button navigates to /project/{id}/settings", async () => {
    renderList();
    const gearButtons = screen.getAllByTitle("Ustawienia projektu");
    await userEvent.click(gearButtons[0]);
    expect(mockPush).toHaveBeenCalledWith("/project/p1/settings");
  });

  it("clicking the gear button does not also navigate to /chat/{id}", async () => {
    renderList();
    const gearButtons = screen.getAllByTitle("Ustawienia projektu");
    await userEvent.click(gearButtons[0]);
    expect(mockPush).not.toHaveBeenCalledWith("/chat/p1");
  });

  it("running project shows pulsing gold dot", () => {
    renderList({ runningProjects: new Set(["p1"]) });
    // The dot element has animate-pulse class
    const dots = document.querySelectorAll(".animate-pulse");
    expect(dots.length).toBeGreaterThan(0);
  });
});
