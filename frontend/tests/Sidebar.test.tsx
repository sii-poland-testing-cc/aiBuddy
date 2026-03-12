import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ── Mock next/navigation ───────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// ── Mock useProjects hook ──────────────────────────────────────────────────

const mockCreateProject = vi.fn();

vi.mock("../lib/useProjects", () => ({
  useProjects: () => ({
    projects: [
      {
        project_id: "proj-123",
        name: "ICE Services DIF",
        created_at: "2025-01-15T12:00:00Z",
        files: [],
      },
    ],
    createProject: mockCreateProject,
  }),
}));

import Sidebar from "../components/Sidebar";

const BASE_PROPS = {
  activeProjectId: "proj-123",
  projectFiles: [],
  onUploadFiles: vi.fn().mockResolvedValue([]),
  isUploading: false,
};

describe("Sidebar — module switcher", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockCreateProject.mockClear();
  });

  it("renders both module buttons", () => {
    render(<Sidebar {...BASE_PROPS} contextReady={true} activeModule="m1" />);
    // Both labels appear in the module switcher section
    expect(screen.getAllByText("Context Builder").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Suite Analyzer")).toBeTruthy();
  });

  it("shows 🔒 on locked modules when contextReady=false", () => {
    render(<Sidebar {...BASE_PROPS} contextReady={false} activeModule="m1" />);
    expect(screen.getAllByText("🔒").length).toBeGreaterThanOrEqual(1);
  });

  it("does NOT show 🔒 when contextReady=true", () => {
    render(<Sidebar {...BASE_PROPS} contextReady={true} activeModule="m1" />);
    expect(screen.queryByText("🔒")).toBeNull();
  });

  it("shows ✓ next to Context Builder when contextReady=true", () => {
    render(<Sidebar {...BASE_PROPS} contextReady={true} activeModule="m1" />);
    // The checkmark appears in the module switcher for m1 when context is ready
    const checks = screen.getAllByText("✓");
    expect(checks.length).toBeGreaterThan(0);
  });

  it("clicking Suite Analyzer when locked does NOT navigate", async () => {
    render(<Sidebar {...BASE_PROPS} contextReady={false} activeModule="m1" />);
    const suiteBtn = screen.getByText("Suite Analyzer").closest("button");
    expect(suiteBtn).toBeTruthy();
    await userEvent.click(suiteBtn!);
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("clicking Context Builder navigates to /context/{id}", async () => {
    render(<Sidebar {...BASE_PROPS} contextReady={true} activeModule="m2" />);
    // The module-switcher button has the 🧠 icon — find it by role within the modules section
    const allContextLabels = screen.getAllByText("Context Builder");
    // First occurrence is in the module switcher (has a parent button with the 🧠 icon)
    const moduleBtn = allContextLabels
      .map((el) => el.closest("button"))
      .find((btn) => btn?.textContent?.includes("🧠"));
    expect(moduleBtn).toBeTruthy();
    await userEvent.click(moduleBtn!);
    expect(mockPush).toHaveBeenCalledWith(
      expect.stringContaining("/context/")
    );
  });

  it("active module m1 highlights Context Builder", () => {
    const { container } = render(
      <Sidebar {...BASE_PROPS} contextReady={true} activeModule="m1" />
    );
    // Active item has border-buddy-gold class applied
    const activeBtn = container.querySelector(".border-buddy-gold");
    expect(activeBtn).toBeTruthy();
  });

  it("clicking '+ Nowy projekt' shows the inline creation form", async () => {
    render(<Sidebar {...BASE_PROPS} contextReady={true} activeModule="m1" />);
    await userEvent.click(screen.getByText(/Nowy projekt/));
    expect(screen.getByPlaceholderText("Nazwa projektu")).toBeTruthy();
  });

  it("submitting a project name calls createProject and navigates", async () => {
    mockCreateProject.mockResolvedValue({
      project_id: "proj-new",
      name: "My New Project",
    });

    render(<Sidebar {...BASE_PROPS} contextReady={true} activeModule="m1" />);

    // Open the creation form
    await userEvent.click(screen.getByText(/Nowy projekt/));

    // Type the project name
    const input = screen.getByPlaceholderText("Nazwa projektu");
    await userEvent.type(input, "My New Project");

    // Click the ✓ submit button
    await userEvent.click(screen.getByRole("button", { name: "✓" }));

    expect(mockCreateProject).toHaveBeenCalledWith("My New Project");
    expect(mockPush).toHaveBeenCalledWith(
      expect.stringContaining("/chat/proj-new")
    );
  });

  it("does NOT navigate when createProject returns null (backend error)", async () => {
    mockCreateProject.mockResolvedValue(null);

    render(<Sidebar {...BASE_PROPS} contextReady={true} activeModule="m1" />);
    await userEvent.click(screen.getByText(/Nowy projekt/));
    const input = screen.getByPlaceholderText("Nazwa projektu");
    await userEvent.type(input, "Broken Project");
    await userEvent.click(screen.getByRole("button", { name: "✓" }));

    expect(mockCreateProject).toHaveBeenCalledWith("Broken Project");
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("pressing Escape cancels the creation form", async () => {
    render(<Sidebar {...BASE_PROPS} contextReady={true} activeModule="m1" />);
    await userEvent.click(screen.getByText(/Nowy projekt/));
    expect(screen.getByPlaceholderText("Nazwa projektu")).toBeTruthy();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByPlaceholderText("Nazwa projektu")).toBeNull();
  });
});
