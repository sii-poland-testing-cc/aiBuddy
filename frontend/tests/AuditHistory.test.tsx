import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AuditHistory from "../components/AuditHistory";

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeSnapshot(id: string, overrides: Record<string, any> = {}) {
  return {
    id,
    created_at: "2024-03-11T14:23:00Z",
    files_used: ["./data/uploads/p1/suite.csv"],
    summary: {
      coverage_pct: overrides.coverage_pct ?? 75,
      duplicates_found: 2,
      requirements_total: 10,
      requirements_covered: 7,
    },
    requirements_uncovered: [],
    recommendations: ["Add edge cases"],
    diff: overrides.diff ?? null,
    ...overrides,
  };
}

const SNAP_A = makeSnapshot("snap-a", { coverage_pct: 75 });
const SNAP_B = makeSnapshot("snap-b", {
  coverage_pct: 60,
  diff: { coverage_delta: -15, duplicates_delta: 1, new_covered: [], newly_uncovered: ["FR-007"], files_added: [], files_removed: [] },
});
const SNAP_C = makeSnapshot("snap-c", { coverage_pct: 85 });

// ── Mock helpers ──────────────────────────────────────────────────────────────

function mockFetch(snapshots: object[], trend?: object) {
  const trendData = trend ?? {
    labels: snapshots.map(() => "2024-03-11T14:23:00Z"),
    coverage: snapshots.map(() => 75),
    duplicates: snapshots.map(() => 2),
  };

  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.includes("/trend")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(trendData) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(snapshots) });
    })
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

afterEach(() => vi.unstubAllGlobals());

describe("AuditHistory", () => {
  it("test_empty_state", async () => {
    mockFetch([]);
    render(<AuditHistory projectId="p1" />);

    // Header always visible
    expect(screen.getByText(/Historia audytów/)).toBeTruthy();

    // Expand panel
    await userEvent.click(screen.getByText(/Historia audytów/));

    await waitFor(() => {
      expect(screen.getByText("Brak zapisanych audytów.")).toBeTruthy();
    });
    expect(screen.queryAllByTestId("snapshot-row")).toHaveLength(0);
  });

  it("test_snapshots_rendered", async () => {
    mockFetch([SNAP_A, SNAP_B, SNAP_C]);
    render(<AuditHistory projectId="p1" />);

    // Expand panel
    await userEvent.click(screen.getByText(/Historia audytów/));

    await waitFor(() => {
      expect(screen.getAllByTestId("snapshot-row")).toHaveLength(3);
    });

    // Dates rendered (time may shift with timezone, match just the day+month)
    const dates = screen.getAllByText(/11 mar/);
    expect(dates.length).toBeGreaterThanOrEqual(3);

    // Coverage badges rendered
    const badges = screen.getAllByTestId("coverage-badge");
    expect(badges).toHaveLength(3);
  });

  it("test_latest_snapshot_highlighted", async () => {
    mockFetch([SNAP_A, SNAP_B]);
    render(<AuditHistory projectId="p1" latestSnapshotId="snap-a" />);

    await userEvent.click(screen.getByText(/Historia audytów/));

    await waitFor(() => {
      expect(screen.getAllByTestId("snapshot-row")).toHaveLength(2);
    });

    const rows = screen.getAllByTestId("snapshot-row");
    // First row (snap-a) should have amber left border (rgb(200, 144, 42) = #c8902a)
    expect(rows[0].style.borderLeft).toMatch(/200, 144, 42|#c8902a/);
    // Second row (snap-b) should have transparent border
    expect(rows[1].style.borderLeft).toContain("transparent");
  });

  it("test_coverage_badge_colors", async () => {
    const GREEN = makeSnapshot("g", { coverage_pct: 85 });
    const AMBER = makeSnapshot("a", { coverage_pct: 60 });
    const RED   = makeSnapshot("r", { coverage_pct: 30 });

    mockFetch([GREEN, AMBER, RED]);
    render(<AuditHistory projectId="p1" />);
    await userEvent.click(screen.getByText(/Historia audytów/));

    await waitFor(() => {
      expect(screen.getAllByTestId("coverage-badge")).toHaveLength(3);
    });

    const badges = screen.getAllByTestId("coverage-badge");
    expect(badges[0].style.color).toBe("rgb(74, 158, 107)");   // green
    expect(badges[1].style.color).toBe("rgb(200, 144, 42)");   // amber
    expect(badges[2].style.color).toBe("rgb(200, 90, 58)");    // red
  });

  it("test_trend_chart_requires_two_snapshots", async () => {
    // 1 snapshot → no chart
    mockFetch([SNAP_A], { labels: ["2024-03-11T14:23:00Z"], coverage: [75], duplicates: [2] });
    const { unmount } = render(<AuditHistory projectId="p1" />);
    await userEvent.click(screen.getByText(/Historia audytów/));
    await waitFor(() => {
      expect(screen.getAllByTestId("snapshot-row")).toHaveLength(1);
    });
    expect(screen.queryByTestId("trend-chart")).toBeNull();
    unmount();

    vi.unstubAllGlobals();

    // 2 snapshots → chart rendered
    mockFetch([SNAP_A, SNAP_B], {
      labels: ["2024-03-11T14:23:00Z", "2024-03-12T10:00:00Z"],
      coverage: [75, 60],
      duplicates: [2, 3],
    });
    render(<AuditHistory projectId="p1" />);
    await userEvent.click(screen.getByText(/Historia audytów/));
    await waitFor(() => {
      expect(screen.getByTestId("trend-chart")).toBeTruthy();
    });
  });
});
