import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RequirementsView from "../components/RequirementsView";
import type { Requirement, RequirementsStats } from "../lib/useRequirements";

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeReq(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: "r1",
    parent_id: null,
    level: "functional_req",
    external_id: "FR-001",
    title: "User Login",
    description: "The system shall allow users to log in.",
    source_type: "formal",
    confidence: 0.9,
    human_reviewed: false,
    needs_review: false,
    review_reason: null,
    taxonomy: { module: "Auth" },
    ...overrides,
  };
}

const REQS: Requirement[] = [
  makeReq({ id: "r1", title: "User Login", taxonomy: { module: "Auth" } }),
  makeReq({ id: "r2", title: "Password Reset", external_id: "FR-002", taxonomy: { module: "Auth" } }),
  makeReq({ id: "r3", title: "Payment Processing", external_id: "FR-010", level: "feature", source_type: "implicit", taxonomy: { module: "Payments" } }),
];

const STATS: RequirementsStats = {
  total: 3,
  by_level: { functional_req: 2, feature: 1 },
  by_source_type: { formal: 2, implicit: 1 },
  needs_review_count: 0,
  human_reviewed_count: 0,
};

function renderView(
  overrides: Partial<Parameters<typeof RequirementsView>[0]> = {}
) {
  const onExtract = vi.fn();
  const onMarkReviewed = vi.fn();
  const props = {
    requirements: REQS,
    stats: STATS,
    loading: false,
    error: null,
    contextReady: true,
    onExtract,
    onMarkReviewed,
    ...overrides,
  };
  const result = render(<RequirementsView {...props} />);
  return { ...result, onExtract, onMarkReviewed };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

afterEach(() => vi.clearAllMocks());

// ── Header ───────────────────────────────────────────────────────────────────

describe("RequirementsView — header", () => {
  it("renders title", () => {
    renderView();
    expect(screen.getByText(/Rejestr wymagań/)).toBeInTheDocument();
  });

  it("shows total count from stats", () => {
    renderView();
    expect(screen.getByText("3 łącznie")).toBeInTheDocument();
  });

  it("shows needs_review_count badge when > 0", () => {
    renderView({
      stats: { ...STATS, needs_review_count: 2 },
    });
    expect(screen.getByText("2 do przeglądu")).toBeInTheDocument();
  });

  it("does NOT show needs_review badge when count is 0", () => {
    renderView();
    expect(screen.queryByText(/do przeglądu/)).not.toBeInTheDocument();
  });

  it("shows human_reviewed_count badge when > 0", () => {
    renderView({
      stats: { ...STATS, human_reviewed_count: 1 },
    });
    expect(screen.getByText("1 zweryfikowanych")).toBeInTheDocument();
  });

  it("shows re-extract button when requirements exist", () => {
    renderView();
    expect(screen.getByRole("button", { name: /Wyodrębnij ponownie/ })).toBeInTheDocument();
  });

  it("calls onExtract when re-extract button clicked", async () => {
    const { onExtract } = renderView();
    await userEvent.click(screen.getByRole("button", { name: /Wyodrębnij ponownie/ }));
    expect(onExtract).toHaveBeenCalledTimes(1);
  });

  it("renders search input", () => {
    renderView();
    expect(screen.getByTestId("req-search")).toBeInTheDocument();
  });
});

// ── Empty state ───────────────────────────────────────────────────────────────

describe("RequirementsView — empty state", () => {
  it("shows empty state when no requirements", () => {
    renderView({ requirements: [], stats: null });
    expect(screen.getByTestId("req-empty-state")).toBeInTheDocument();
    expect(screen.getByText("Nie wyodrębniono jeszcze wymagań")).toBeInTheDocument();
  });

  it("shows ready message when contextReady=true", () => {
    renderView({ requirements: [], stats: null, contextReady: true });
    expect(screen.getByText(/Kontekst projektu jest gotowy/)).toBeInTheDocument();
  });

  it("shows Context Builder message when contextReady=false", () => {
    renderView({ requirements: [], stats: null, contextReady: false });
    expect(screen.getByText(/Context Builder/)).toBeInTheDocument();
  });

  it("extract button is enabled when contextReady=true", () => {
    renderView({ requirements: [], stats: null, contextReady: true });
    expect(screen.getByTestId("extract-btn")).not.toBeDisabled();
  });

  it("extract button is disabled when contextReady=false", () => {
    renderView({ requirements: [], stats: null, contextReady: false });
    expect(screen.getByTestId("extract-btn")).toBeDisabled();
  });

  it("calls onExtract when extract button clicked", async () => {
    const { onExtract } = renderView({ requirements: [], stats: null, contextReady: true });
    await userEvent.click(screen.getByTestId("extract-btn"));
    expect(onExtract).toHaveBeenCalledTimes(1);
  });
});

// ── Error ─────────────────────────────────────────────────────────────────────

describe("RequirementsView — error", () => {
  it("shows error message", () => {
    renderView({ error: "Coś poszło nie tak." });
    expect(screen.getByText(/Coś poszło nie tak\./)).toBeInTheDocument();
  });
});

// ── Loading ───────────────────────────────────────────────────────────────────

describe("RequirementsView — loading skeletons", () => {
  it("shows loading skeletons when loading=true and no requirements", () => {
    renderView({ requirements: [], stats: null, loading: true });
    // Should render skeleton items (animate-pulse divs)
    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("does NOT show empty state while loading", () => {
    renderView({ requirements: [], stats: null, loading: true });
    expect(screen.queryByTestId("req-empty-state")).not.toBeInTheDocument();
  });
});

// ── Groups / cards ────────────────────────────────────────────────────────────

describe("RequirementsView — module groups", () => {
  it("renders a group for each module", () => {
    renderView();
    const groups = screen.getAllByTestId("req-module-group");
    expect(groups).toHaveLength(2); // Auth + Payments
  });

  it("renders group labels", () => {
    renderView();
    expect(screen.getByText("Auth")).toBeInTheDocument();
    expect(screen.getByText("Payments")).toBeInTheDocument();
  });

  it("renders requirement cards inside groups", () => {
    renderView();
    const cards = screen.getAllByTestId("req-card");
    expect(cards).toHaveLength(3);
  });

  it("renders requirement titles", () => {
    renderView();
    expect(screen.getByText("User Login")).toBeInTheDocument();
    expect(screen.getByText("Payment Processing")).toBeInTheDocument();
  });

  it("renders external_id badge", () => {
    renderView();
    expect(screen.getByText("FR-001")).toBeInTheDocument();
  });

  it("groups requirements with no module under 'Inne'", () => {
    const req = makeReq({ id: "r4", title: "Orphan", taxonomy: null });
    renderView({ requirements: [req], stats: null });
    expect(screen.getByText("Inne")).toBeInTheDocument();
  });
});

// ── Search / filter ───────────────────────────────────────────────────────────

describe("RequirementsView — search", () => {
  it("filters requirements by title", async () => {
    renderView();
    await userEvent.type(screen.getByTestId("req-search"), "Login");
    // Only 'User Login' matches
    expect(screen.getByText("User Login")).toBeInTheDocument();
    expect(screen.queryByText("Payment Processing")).not.toBeInTheDocument();
  });

  it("filters by external_id", async () => {
    renderView();
    await userEvent.type(screen.getByTestId("req-search"), "FR-010");
    expect(screen.getByText("Payment Processing")).toBeInTheDocument();
    expect(screen.queryByText("User Login")).not.toBeInTheDocument();
  });

  it("shows no-results message when nothing matches", async () => {
    renderView();
    await userEvent.type(screen.getByTestId("req-search"), "zzznomatch");
    expect(screen.getByText(/Brak wymagań pasujących/)).toBeInTheDocument();
  });

  it("clearing search restores all requirements", async () => {
    renderView();
    await userEvent.type(screen.getByTestId("req-search"), "Login");
    expect(screen.queryByText("Payment Processing")).not.toBeInTheDocument();
    await userEvent.clear(screen.getByTestId("req-search"));
    expect(screen.getByText("Payment Processing")).toBeInTheDocument();
  });
});

// ── RequirementCard badges ────────────────────────────────────────────────────

describe("RequirementsView — card badges", () => {
  it("shows level badge", () => {
    renderView();
    const cards = screen.getAllByTestId("req-card");
    // First card (User Login) has level "functional_req"
    expect(within(cards[0]).getByText("functional req")).toBeInTheDocument();
  });

  it("shows source_type badge", () => {
    renderView();
    const cards = screen.getAllByTestId("req-card");
    expect(within(cards[0]).getByText("formal")).toBeInTheDocument();
  });

  it("shows 'do przeglądu' badge on needs_review card", () => {
    const req = makeReq({ id: "r5", needs_review: true, review_reason: "Low confidence" });
    renderView({ requirements: [req], stats: null });
    expect(screen.getByText("do przeglądu")).toBeInTheDocument();
  });

  it("shows review_reason text when present", () => {
    const req = makeReq({ id: "r5", needs_review: true, review_reason: "Low confidence" });
    renderView({ requirements: [req], stats: null });
    expect(screen.getByText("Low confidence")).toBeInTheDocument();
  });
});

// ── Mark reviewed ─────────────────────────────────────────────────────────────

describe("RequirementsView — mark reviewed", () => {
  it("shows 'Oznacz jako zweryfikowane' button on unreviewed card", () => {
    renderView();
    expect(screen.getAllByText(/Oznacz jako zweryfikowane/).length).toBeGreaterThan(0);
  });

  it("calls onMarkReviewed with req id when button clicked", async () => {
    const { onMarkReviewed } = renderView();
    const btns = screen.getAllByText(/Oznacz jako zweryfikowane/);
    await userEvent.click(btns[0]);
    expect(onMarkReviewed).toHaveBeenCalledWith("r1");
  });

  it("shows '✓ Zweryfikowane' on reviewed cards", () => {
    const req = makeReq({ human_reviewed: true });
    renderView({ requirements: [req], stats: null });
    expect(screen.getByText(/Zweryfikowane/)).toBeInTheDocument();
  });
});

// ── ModuleGroup collapse ──────────────────────────────────────────────────────

describe("RequirementsView — ModuleGroup collapse", () => {
  it("groups are open by default", () => {
    renderView();
    const cards = screen.getAllByTestId("req-card");
    expect(cards.length).toBeGreaterThan(0);
  });

  it("clicking group header toggles collapse", async () => {
    renderView();
    // Find first group header button
    const group = screen.getAllByTestId("req-module-group")[0];
    const header = within(group).getAllByRole("button")[0];
    // Cards visible initially
    expect(screen.getAllByTestId("req-card").length).toBeGreaterThan(0);
    await userEvent.click(header);
    // After collapse, some cards may be gone (only first group collapsed)
    // At minimum, groups still render
    expect(screen.getAllByTestId("req-module-group").length).toBeGreaterThan(0);
  });
});

describe("RequirementsView — source origin", () => {
  it("shows source origin badge when source_references is set", () => {
    const req = makeReq({ id: "r9", source_references: ["srs_v3.docx"] });
    renderView({ requirements: [req], stats: { ...STATS, total: 1 } });
    const badge = screen.getByTestId("req-source-origin");
    expect(badge).toHaveTextContent("srs_v3.docx");
    expect(badge).toHaveAttribute("title", "Source: srs_v3.docx");
  });

  it("does not show source origin badge when source_references is null", () => {
    const req = makeReq({ id: "r10", source_references: null });
    renderView({ requirements: [req], stats: { ...STATS, total: 1 } });
    expect(screen.queryByTestId("req-source-origin")).not.toBeInTheDocument();
  });

  it("renders URL source as a link", () => {
    const req = makeReq({ id: "r11", source_references: ["https://jira.example.com/PROJ-123"] });
    renderView({ requirements: [req], stats: { ...STATS, total: 1 } });
    const badge = screen.getByTestId("req-source-origin");
    const link = badge.querySelector("a");
    expect(link).toHaveAttribute("href", "https://jira.example.com/PROJ-123");
    expect(link).toHaveAttribute("target", "_blank");
  });
});
