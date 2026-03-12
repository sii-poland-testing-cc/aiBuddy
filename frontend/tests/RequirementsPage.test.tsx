import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ── Next.js mocks ──────────────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// ── Component / hook mocks ─────────────────────────────────────────────────────

vi.mock("../components/Sidebar", () => ({
  default: () => <nav data-testid="sidebar" />,
}));

vi.mock("../components/ErrorBanner", () => ({
  default: ({ message }: { message: string }) => (
    <div data-testid="error-banner">{message}</div>
  ),
}));

vi.mock("../lib/useProjectFiles", () => ({
  useProjectFiles: () => ({ files: [], uploading: false, uploadFiles: vi.fn() }),
}));

vi.mock("../lib/useHeatmap", () => ({
  useHeatmap: () => ({ heatmap: [], loading: false, error: null, retry: vi.fn() }),
}));

const mockUseContextBuilder = vi.fn();
vi.mock("../lib/useContextBuilder", () => ({
  useContextBuilder: () => mockUseContextBuilder(),
}));

const mockExtractRequirements = vi.fn();
const mockUseRequirements = vi.fn();
vi.mock("../lib/useRequirements", () => ({
  useRequirements: () => mockUseRequirements(),
}));

// ── Import page after mocks ────────────────────────────────────────────────────

import RequirementsPage from "../app/requirements/[projectId]/page";

// ── Helpers ───────────────────────────────────────────────────────────────────

function baseRequirementsHook(overrides = {}) {
  return {
    requirements: [],
    stats: null,
    loading: false,
    error: null,
    isExtracting: false,
    extractionProgress: null,
    patchRequirement: vi.fn(),
    extractRequirements: mockExtractRequirements,
    retry: vi.fn(),
    ...overrides,
  };
}

function renderPage(projectId = "proj-1") {
  return render(<RequirementsPage params={{ projectId }} />);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("RequirementsPage — header extract button", () => {
  beforeEach(() => {
    mockExtractRequirements.mockReset();
    mockPush.mockReset();
  });

  it("shows 'Wyodrębnij wymagania' when context is ready and no requirements", () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: true } });
    mockUseRequirements.mockReturnValue(baseRequirementsHook());

    renderPage();

    // Both header AND empty-state render this button when contextReady=true + no requirements
    const buttons = screen.getAllByRole("button", { name: "Wyodrębnij wymagania" });
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });

  it("shows '↺ Wyodrębnij ponownie' when requirements already exist", () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: true } });
    mockUseRequirements.mockReturnValue(
      baseRequirementsHook({
        requirements: [
          { id: "r1", title: "FR-001", level: "functional_req", confidence: 0.9,
            human_reviewed: false, needs_review: false, description: "",
            source_type: "explicit", parent_id: null, external_id: "FR-001",
            review_reason: null, taxonomy: null },
        ],
        stats: { total: 1, by_level: {}, by_source_type: {}, needs_review_count: 0, human_reviewed_count: 0 },
      })
    );

    renderPage();

    expect(screen.getByRole("button", { name: "↺ Wyodrębnij ponownie" })).toBeInTheDocument();
  });

  it("shows 'Wyodrębnianie…' and disables button while extracting", () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: true } });
    mockUseRequirements.mockReturnValue(
      baseRequirementsHook({
        isExtracting: true,
        extractionProgress: { message: "Przetwarzanie…", progress: 0.3, stage: "extract" },
      })
    );

    renderPage();

    // Both header and empty-state render "Wyodrębnianie…" while extracting;
    // the header button must be disabled
    const buttons = screen.getAllByRole("button", { name: "Wyodrębnianie…" });
    expect(buttons.length).toBeGreaterThanOrEqual(1);
    expect(buttons[0]).toBeDisabled();
  });

  it("disables button when context is not ready", () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: false } });
    mockUseRequirements.mockReturnValue(baseRequirementsHook());

    renderPage();

    const btn = screen.getByRole("button", { name: "Wyodrębnij wymagania" });
    expect(btn).toBeDisabled();
  });

  it("calls extractRequirements when header button is clicked", async () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: true } });
    mockUseRequirements.mockReturnValue(baseRequirementsHook());

    renderPage();

    // Pick the first (header) button — both header and empty-state are labelled the same
    const buttons = screen.getAllByRole("button", { name: "Wyodrębnij wymagania" });
    await userEvent.click(buttons[0]);
    expect(mockExtractRequirements).toHaveBeenCalledTimes(1);
  });
});

describe("RequirementsPage — extraction progress bar", () => {
  it("shows progress bar with message and percentage when extracting", () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: true } });
    mockUseRequirements.mockReturnValue(
      baseRequirementsHook({
        isExtracting: true,
        extractionProgress: { message: "Analizowanie dokumentów…", progress: 0.4, stage: "extract" },
      })
    );

    renderPage();

    expect(screen.getByText("Analizowanie dokumentów…")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
  });

  it("does not show progress bar when not extracting", () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: true } });
    mockUseRequirements.mockReturnValue(baseRequirementsHook());

    renderPage();

    expect(screen.queryByText("40%")).not.toBeInTheDocument();
  });
});

describe("RequirementsPage — empty state", () => {
  it("shows extract button in empty state when contextReady=true", () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: true } });
    mockUseRequirements.mockReturnValue(baseRequirementsHook());

    renderPage();

    // The empty state renders its own extract button (inside RequirementsRegistry)
    const buttons = screen.getAllByRole("button", { name: "Wyodrębnij wymagania" });
    // at least the header button, possibly the empty-state button too
    expect(buttons.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Nie wyodrębniono jeszcze wymagań")).toBeInTheDocument();
    expect(screen.getByText(/Kontekst projektu jest gotowy/)).toBeInTheDocument();
  });

  it("shows Context Builder link in empty state when contextReady=false", () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: false } });
    mockUseRequirements.mockReturnValue(baseRequirementsHook());

    renderPage();

    expect(screen.getByRole("button", { name: /Przejdź do Context Builder/ })).toBeInTheDocument();
    expect(screen.queryByText(/Kontekst projektu jest gotowy/)).not.toBeInTheDocument();
  });

  it("navigates to context builder when empty-state button is clicked and context not ready", async () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: false } });
    mockUseRequirements.mockReturnValue(baseRequirementsHook());

    renderPage("my-project");

    await userEvent.click(screen.getByRole("button", { name: /Przejdź do Context Builder/ }));
    expect(mockPush).toHaveBeenCalledWith("/context/my-project");
  });

  it("calls extractRequirements when empty-state extract button is clicked", async () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: true } });
    mockUseRequirements.mockReturnValue(baseRequirementsHook());

    renderPage();

    // Click the empty-state button (last "Wyodrębnij wymagania" button rendered)
    const buttons = screen.getAllByRole("button", { name: "Wyodrębnij wymagania" });
    await userEvent.click(buttons[buttons.length - 1]);
    expect(mockExtractRequirements).toHaveBeenCalled();
  });
});

describe("RequirementsPage — error banner", () => {
  it("shows error banner when reqError is set", () => {
    mockUseContextBuilder.mockReturnValue({ status: { rag_ready: true } });
    mockUseRequirements.mockReturnValue(
      baseRequirementsHook({ error: "Nie udało się pobrać wymagań." })
    );

    renderPage();

    expect(screen.getByTestId("error-banner")).toHaveTextContent("Nie udało się pobrać wymagań.");
  });
});
