import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UtilityPanel, { PanelFile, AuditSnapshot } from "../components/UtilityPanel";
import type { HeatmapRow } from "../lib/useHeatmap";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const FILES: PanelFile[] = [
  { id: "f1", filename: "new_suite.xlsx", file_path: "/f1", source_type: "file", selected: true,  isNew: true  },
  { id: "f2", filename: "old_tests.csv",  file_path: "/f2", source_type: "file", selected: false, isNew: false },
  { id: "f3", filename: "conf_page",      file_path: "/f3", source_type: "confluence", selected: true, isNew: false },
];

const GLOSSARY = [
  { term: "3DS Verification", definition: "Auth protocol.", related_terms: [], source: "doc.docx" },
  { term: "Acquirer",         definition: "Acquiring bank.", related_terms: [], source: "doc.docx" },
];

const HEATMAP: HeatmapRow[] = [
  { module: "Payment", total_requirements: 12, covered: 10, avg_score: 82.5, color: "green" },
  { module: "Auth",    total_requirements: 8,  covered: 5,  avg_score: 55.0, color: "orange" },
];

const SNAPSHOTS: AuditSnapshot[] = [
  { id: "s1", created_at: "2026-03-18T14:00:00Z", summary: { coverage_pct: 71 }, diff: { coverage_delta: 8 } },
  { id: "s2", created_at: "2026-03-10T10:00:00Z", summary: { coverage_pct: 58 }, diff: null },
];

function renderPanel(
  mode: "context" | "requirements" | "audit",
  overrides: Partial<Parameters<typeof UtilityPanel>[0]> = {}
) {
  const props = {
    open: true,
    activeMode: mode,
    projectId: "p1",
    ...overrides,
  };
  return render(<UtilityPanel {...props} />);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("UtilityPanel", () => {
  afterEach(() => vi.clearAllMocks());

  // ── Visibility ──────────────────────────────────────────────────────────────

  it("renders panel when open=true", () => {
    renderPanel("context");
    expect(screen.getByTestId("utility-panel")).toBeInTheDocument();
  });

  it("panel has width:0 when open=false", () => {
    render(
      <UtilityPanel open={false} activeMode="context" projectId="p1" />
    );
    const panel = screen.getByTestId("utility-panel");
    expect(panel.style.width).toBe("0px");
  });

  // ── Mode switching ──────────────────────────────────────────────────────────

  it("shows context cards when activeMode=context", () => {
    renderPanel("context");
    expect(screen.getByTestId("panel-mode-context")).toBeInTheDocument();
    expect(screen.queryByTestId("panel-mode-requirements")).not.toBeInTheDocument();
    expect(screen.queryByTestId("panel-mode-audit")).not.toBeInTheDocument();
  });

  it("shows requirements cards when activeMode=requirements", () => {
    renderPanel("requirements");
    expect(screen.getByTestId("panel-mode-requirements")).toBeInTheDocument();
    expect(screen.queryByTestId("panel-mode-context")).not.toBeInTheDocument();
  });

  it("shows audit cards when activeMode=audit", () => {
    renderPanel("audit");
    expect(screen.getByTestId("panel-mode-audit")).toBeInTheDocument();
    expect(screen.queryByTestId("panel-mode-context")).not.toBeInTheDocument();
  });

  // ── PanelCard toggle ────────────────────────────────────────────────────────

  it("clicking a closed card header opens the body", async () => {
    renderPanel("context");
    // "Status kontekstu" card is closed by default
    const card = screen.getByTestId("card-ctx-status");
    expect(within(card).queryByText("Brak danych o kontekście.")).not.toBeInTheDocument();

    await userEvent.click(within(card).getByRole("button"));
    expect(within(card).getByText("Brak danych o kontekście.")).toBeInTheDocument();
  });

  // ── Sources card ────────────────────────────────────────────────────────────

  // SourcesCard with auditFiles is used in audit/requirements mode.
  // Context mode derives its file list from contextStatus.context_files instead.

  it("renders new and used file sections in sources card (audit mode)", () => {
    renderPanel("audit", { auditFiles: FILES });
    expect(screen.getByText("Nowe")).toBeInTheDocument();
    expect(screen.getByText("Poprzednio użyte")).toBeInTheDocument();
    expect(screen.getByText("new_suite.xlsx")).toBeInTheDocument();
    expect(screen.getByText("old_tests.csv")).toBeInTheDocument();
  });

  it("NEW badge visible only for new files (audit mode)", () => {
    renderPanel("audit", { auditFiles: FILES });
    expect(screen.getByText("NEW")).toBeInTheDocument();
  });

  it("switching to Links tab shows link sources (audit mode)", async () => {
    renderPanel("audit", { auditFiles: FILES });
    await userEvent.click(screen.getByTestId("src-tab-links"));
    expect(screen.getByText("conf_page")).toBeInTheDocument();
  });

  it("context mode sources card shows contextStatus.context_files, not auditFiles", () => {
    const contextStatus = {
      project_id: "p1",
      rag_ready: true,
      artefacts_ready: true,
      stats: null,
      context_files: ["srs_payment.docx", "test_plan.docx"],
    };
    renderPanel("context", { auditFiles: FILES, contextStatus });
    expect(screen.getByText("srs_payment.docx")).toBeInTheDocument();
    expect(screen.getByText("test_plan.docx")).toBeInTheDocument();
    // audit test files must NOT appear in context sources
    expect(screen.queryByText("new_suite.xlsx")).not.toBeInTheDocument();
  });

  it("+ Dodaj pliki button calls onAddFiles", async () => {
    const onAddFiles = vi.fn();
    renderPanel("context", { auditFiles: FILES, onAddFiles });
    await userEvent.click(screen.getByText("+ Dodaj pliki"));
    expect(onAddFiles).toHaveBeenCalledTimes(1);
  });

  // ── Mind map thumbnail ──────────────────────────────────────────────────────

  it("renders mind map thumbnail in context mode", () => {
    renderPanel("context");
    expect(screen.getByTestId("mindmap-thumbnail")).toBeInTheDocument();
  });

  it("clicking thumbnail calls onOpenMindMap", async () => {
    const onOpenMindMap = vi.fn();
    renderPanel("context", { onOpenMindMap });
    await userEvent.click(screen.getByTestId("mindmap-thumbnail"));
    expect(onOpenMindMap).toHaveBeenCalledTimes(1);
  });

  // ── Glossary ────────────────────────────────────────────────────────────────

  it("renders glossary terms", async () => {
    renderPanel("context", { glossary: GLOSSARY });
    // Glossary card is closed by default — open it
    const card = screen.getByTestId("card-glossary");
    await userEvent.click(within(card).getByRole("button"));
    expect(screen.getByText("3DS Verification")).toBeInTheDocument();
    expect(screen.getByText("Acquirer")).toBeInTheDocument();
  });

  it("glossary search filters terms", async () => {
    renderPanel("context", { glossary: GLOSSARY });
    // Open the glossary card first (it's closed by default — no defaultOpen)
    const card = screen.getByTestId("card-glossary");
    await userEvent.click(within(card).getByRole("button"));

    await userEvent.type(screen.getByTestId("glossary-search"), "Acqui");
    expect(screen.queryByText("3DS Verification")).not.toBeInTheDocument();
    expect(screen.getByText("Acquirer")).toBeInTheDocument();
  });

  it("clicking a glossary term calls onTermClick", async () => {
    const onTermClick = vi.fn();
    renderPanel("context", { glossary: GLOSSARY, onTermClick });
    const card = screen.getByTestId("card-glossary");
    await userEvent.click(within(card).getByRole("button"));

    await userEvent.click(screen.getAllByTestId("glossary-term")[0]);
    expect(onTermClick).toHaveBeenCalledWith("3DS Verification");
  });

  // ── Build mode ──────────────────────────────────────────────────────────────

  it("build mode buttons switch selection", async () => {
    const onBuildModeChange = vi.fn();
    renderPanel("context", { onBuildModeChange });
    const card = screen.getByTestId("card-build-mode");
    await userEvent.click(within(card).getByRole("button")); // open card

    await userEvent.click(screen.getByText(/Rebuild/));
    expect(onBuildModeChange).toHaveBeenCalledWith("rebuild");
  });

  it("▶ Uruchom budowanie calls onBuild with current mode", async () => {
    const onBuild = vi.fn();
    renderPanel("context", { onBuild });
    const card = screen.getByTestId("card-build-mode");
    await userEvent.click(within(card).getByRole("button")); // open card

    await userEvent.click(screen.getByTestId("build-btn"));
    expect(onBuild).toHaveBeenCalledWith("append");
  });

  // ── Heatmap ─────────────────────────────────────────────────────────────────

  it("renders heatmap rows in requirements mode", () => {
    renderPanel("requirements", { heatmapData: HEATMAP });
    expect(screen.getByText("Payment")).toBeInTheDocument();
    expect(screen.getByText("Auth")).toBeInTheDocument();
    expect(screen.getByText("🟢")).toBeInTheDocument();
    expect(screen.getByText("🟠")).toBeInTheDocument();
  });

  it("shows placeholder when heatmap is empty", () => {
    renderPanel("requirements", { heatmapData: [] });
    expect(screen.getByText(/Brak danych heatmapy/)).toBeInTheDocument();
  });

  // ── Audit pipeline button ────────────────────────────────────────────────────

  it("Uruchom audyt button calls onAuditPipeline in audit mode", async () => {
    const onAuditPipeline = vi.fn();
    renderPanel("audit", { onAuditPipeline });
    await userEvent.click(screen.getByTestId("run-audit-pipeline-btn"));
    expect(onAuditPipeline).toHaveBeenCalledTimes(1);
    expect(onAuditPipeline).toHaveBeenCalledWith("Uruchom audyt");
  });

  it("Uruchom audyt button is disabled when onAuditPipeline is not provided", () => {
    renderPanel("audit");
    expect(screen.getByTestId("run-audit-pipeline-btn")).toBeDisabled();
  });

  // ── Mapping (audit mode) ─────────────────────────────────────────────────────

  it("Uruchom mapowanie calls onRunMapping in audit mode", async () => {
    const onRunMapping = vi.fn();
    renderPanel("audit", { onRunMapping });
    await userEvent.click(screen.getByTestId("run-mapping-btn"));
    expect(onRunMapping).toHaveBeenCalledTimes(1);
  });

  it("mapping button is disabled and shows progress while running", () => {
    renderPanel("audit", {
      isMappingRunning: true,
      mappingProgress: { message: "Dopasowywanie…", progress: 0.5, stage: "coarse" },
    });
    const btn = screen.getByTestId("run-mapping-btn");
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent("Mapowanie w toku…");
    expect(screen.getByText("Dopasowywanie…")).toBeInTheDocument();
  });

  // ── Audit snapshots ─────────────────────────────────────────────────────────

  it("renders snapshot rows in audit mode", async () => {
    renderPanel("audit", { snapshots: SNAPSHOTS });
    const card = screen.getByTestId("card-history");
    await userEvent.click(within(card).getByRole("button")); // open card
    expect(screen.getAllByTestId("snapshot-row")).toHaveLength(2);
  });

  it("shows empty state when no snapshots", async () => {
    renderPanel("audit", { snapshots: [] });
    const card = screen.getByTestId("card-history");
    await userEvent.click(within(card).getByRole("button")); // open card
    expect(screen.getByText("Brak historii audytów.")).toBeInTheDocument();
  });

  it("latest snapshot has gold highlight styling", async () => {
    renderPanel("audit", { snapshots: SNAPSHOTS, latestSnapshotId: "s1" });
    const card = screen.getByTestId("card-history");
    await userEvent.click(within(card).getByRole("button")); // open card
    const rows = screen.getAllByTestId("snapshot-row");
    // Latest row has gold border color inline
    expect(rows[0].style.borderColor).toBeTruthy();
  });

  // ── Tier selector ───────────────────────────────────────────────────────────

  it("renders tier buttons in audit mode", async () => {
    renderPanel("audit");
    const card = screen.getByTestId("card-tier");
    await userEvent.click(within(card).getByRole("button")); // open card
    expect(within(card).getByText("Audyt")).toBeInTheDocument();
  });

  it("clicking Optymalizacja calls onTierChange", async () => {
    const onTierChange = vi.fn();
    renderPanel("audit", { tier: "audit", onTierChange });
    const card = screen.getByTestId("card-tier");
    await userEvent.click(within(card).getByRole("button")); // open card

    await userEvent.click(screen.getByText("Optymalizacja"));
    expect(onTierChange).toHaveBeenCalledWith("optimize");
  });

  it("Regeneracja button is disabled", async () => {
    renderPanel("audit");
    const card = screen.getByTestId("card-tier");
    await userEvent.click(within(card).getByRole("button")); // open card

    expect(screen.getByText(/Regeneracja/)).toBeDisabled();
  });
});
