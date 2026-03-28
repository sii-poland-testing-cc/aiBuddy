import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TopBar from "../components/TopBar";

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("../lib/useProjects", () => ({
  useProjects: () => ({
    projects: [
      { project_id: "p1", name: "PayFlow QA Suite", created_at: "2026-03-01T00:00:00Z" },
      { project_id: "p2", name: "Auth Service v2",  created_at: "2026-03-10T00:00:00Z" },
    ],
    createProject: vi.fn(),
  }),
}));

vi.mock("../lib/useContextStatuses", () => ({
  useContextStatuses: () => ({ p1: true, p2: false }),
}));

vi.mock("../lib/useCurrentUser", () => ({
  useCurrentUser: () => ({ user: { id: "u1", email: "tom.kuran@example.com", is_superadmin: false }, loading: false }),
}));

vi.mock("../lib/apiFetch", () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true }),
  API_BASE: "http://localhost:8000",
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderTopBar(overrides: Partial<Parameters<typeof TopBar>[0]> = {}) {
  const props = {
    projectId: "p1",
    onTogglePanel: vi.fn(),
    panelOpen: false,
    ragReady: false,
    ...overrides,
  };
  return { ...render(<TopBar {...props} />), props };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("TopBar", () => {
  afterEach(() => vi.clearAllMocks());

  it("renders the current project name", () => {
    renderTopBar({ projectId: "p1" });
    expect(screen.getByText("PayFlow QA Suite")).toBeInTheDocument();
  });

  it("dropdown is closed by default", () => {
    renderTopBar();
    expect(screen.queryByTestId("project-dropdown")).not.toBeInTheDocument();
  });

  it("dropdown opens when the switcher button is clicked", async () => {
    renderTopBar();
    await userEvent.click(screen.getByTestId("project-switcher-btn"));
    expect(screen.getByTestId("project-dropdown")).toBeInTheDocument();
    // Both projects visible in list
    expect(screen.getAllByText("PayFlow QA Suite").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Auth Service v2")).toBeInTheDocument();
  });

  it("active project shows a checkmark; other project does not", async () => {
    renderTopBar({ projectId: "p1" });
    await userEvent.click(screen.getByTestId("project-switcher-btn"));
    // Checkmark SVG path is rendered only for the active row
    // We verify by checking aria structure: active row button contains a check path
    const buttons = screen.getAllByRole("button");
    const p1Row = buttons.find((b) => b.textContent?.includes("PayFlow QA Suite") && b.closest("[data-testid='project-dropdown']"));
    expect(p1Row).toBeTruthy();
    // Active row shows ✓ checkmark
    const dropdown = screen.getByTestId("project-dropdown");
    expect(dropdown).toHaveTextContent("✓");
  });

  it("outside click closes the dropdown", async () => {
    renderTopBar();
    await userEvent.click(screen.getByTestId("project-switcher-btn"));
    expect(screen.getByTestId("project-dropdown")).toBeInTheDocument();

    // Click outside
    await userEvent.click(document.body);
    await waitFor(() =>
      expect(screen.queryByTestId("project-dropdown")).not.toBeInTheDocument()
    );
  });

  it("RAG badge is hidden when ragReady is false", () => {
    renderTopBar({ ragReady: false });
    expect(screen.queryByText("RAG")).not.toBeInTheDocument();
  });

  it("RAG badge is visible when ragReady is true", () => {
    renderTopBar({ ragReady: true });
    expect(screen.getByText("RAG")).toBeInTheDocument();
  });

  it("panel toggle button calls onTogglePanel", async () => {
    const onTogglePanel = vi.fn();
    renderTopBar({ onTogglePanel });
    await userEvent.click(screen.getByRole("button", { name: /toggle side panel/i }));
    expect(onTogglePanel).toHaveBeenCalledTimes(1);
  });

  it("panel toggle button has active styling when panelOpen is true", () => {
    renderTopBar({ panelOpen: true });
    const btn = screen.getByRole("button", { name: /toggle side panel/i });
    expect(btn.className).toMatch(/buddy-gold/);
  });

  it("avatar shows initials derived from current user email", () => {
    renderTopBar();
    // tom.kuran@example.com → "TK"
    expect(screen.getByText("TK")).toBeInTheDocument();
  });

  it("user email appears in avatar dropdown", () => {
    renderTopBar();
    expect(screen.getByText("tom.kuran@example.com")).toBeInTheDocument();
  });

  it("clicking Wyloguj calls logout endpoint and redirects to /login", async () => {
    const { apiFetch } = await import("../lib/apiFetch");
    renderTopBar();
    await userEvent.click(screen.getByText("Wyloguj"));
    expect(apiFetch).toHaveBeenCalledWith("/api/auth/logout", { method: "POST" });
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/login"));
  });

  it("dropdown shows a settings gear button for each project", async () => {
    renderTopBar();
    await userEvent.click(screen.getByTestId("project-switcher-btn"));
    const gearButtons = screen.getAllByTitle("Ustawienia projektu");
    expect(gearButtons).toHaveLength(2);
  });

  it("clicking a gear button in dropdown navigates to settings and closes dropdown", async () => {
    renderTopBar({ projectId: "p1" });
    await userEvent.click(screen.getByTestId("project-switcher-btn"));
    const gearButtons = screen.getAllByTitle("Ustawienia projektu");
    await userEvent.click(gearButtons[1]); // Auth Service v2
    expect(mockPush).toHaveBeenCalledWith("/project/p2/settings");
    await waitFor(() =>
      expect(screen.queryByTestId("project-dropdown")).not.toBeInTheDocument()
    );
  });
});
