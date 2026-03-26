import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ConflictResolution from "../components/ConflictResolution";

const MOCK_CONFLICT = {
  id: "c1",
  project_id: "p1",
  artifact_type: "requirement" as const,
  artifact_item_id: "req-1",
  source_context_id: "s1",
  target_context_id: "d1",
  incoming_value: { id: "req-1", title: "New title", description: "New description" },
  existing_value: { id: "req-1", title: "Old title", description: "Old description" },
  conflict_reason: "title_mismatch: 'Old title' → 'New title'",
  status: "pending" as const,
  resolved_at: null,
  resolved_by: null,
  resolution_value: null,
  created_at: "2026-03-26T10:00:00Z",
  source_context_name: "Story 1",
  source_context_level: "story",
  target_context_name: "Payment Domain",
  target_context_level: "domain",
};

describe("ConflictResolution", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
      if (url.includes("/resolve")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            conflict: { ...MOCK_CONFLICT, status: "resolved_accept_new" },
            retry_result: null,
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ project_id: "p1", count: 1, conflicts: [MOCK_CONFLICT] }),
      });
    }));
  });
  afterEach(() => { vi.restoreAllMocks(); });

  it("renders closed when open=false", () => {
    render(<ConflictResolution open={false} onClose={vi.fn()} projectId="p1" />);
    expect(screen.queryByTestId("conflict-resolution-panel")).not.toBeInTheDocument();
  });

  it("renders panel when open=true", async () => {
    render(<ConflictResolution open={true} onClose={vi.fn()} projectId="p1" />);
    await waitFor(() => expect(screen.getByTestId("conflict-resolution-panel")).toBeInTheDocument());
  });

  it("shows conflict count in header", async () => {
    render(<ConflictResolution open={true} onClose={vi.fn()} projectId="p1" />);
    await waitFor(() => expect(screen.getByTestId("conflict-count")).toHaveTextContent("1"));
  });

  it("shows conflict row in list", async () => {
    render(<ConflictResolution open={true} onClose={vi.fn()} projectId="p1" />);
    await waitFor(() => expect(screen.getByTestId("conflict-row-c1")).toBeInTheDocument());
  });

  it("clicking conflict row shows diff panel", async () => {
    render(<ConflictResolution open={true} onClose={vi.fn()} projectId="p1" />);
    await waitFor(() => screen.getByTestId("conflict-row-c1"));
    await userEvent.click(screen.getByTestId("conflict-row-c1"));
    expect(screen.getByTestId("conflict-diff-panel")).toBeInTheDocument();
  });

  it("diff panel shows existing and incoming values", async () => {
    render(<ConflictResolution open={true} onClose={vi.fn()} projectId="p1" />);
    await waitFor(() => screen.getByTestId("conflict-row-c1"));
    await userEvent.click(screen.getByTestId("conflict-row-c1"));
    const diff = screen.getByTestId("conflict-diff-panel");
    expect(within(diff).getByTestId("existing-panel")).toBeInTheDocument();
    expect(within(diff).getByTestId("incoming-panel")).toBeInTheDocument();
  });

  it("accept incoming button resolves conflict", async () => {
    render(<ConflictResolution open={true} onClose={vi.fn()} projectId="p1" />);
    await waitFor(() => screen.getByTestId("conflict-row-c1"));
    await userEvent.click(screen.getByTestId("conflict-row-c1"));
    await userEvent.click(screen.getByTestId("resolve-accept-btn"));
    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
      expect(calls.some(([url]: [string]) => url.includes("/resolve"))).toBe(true);
    });
  });

  it("keep current button resolves conflict", async () => {
    render(<ConflictResolution open={true} onClose={vi.fn()} projectId="p1" />);
    await waitFor(() => screen.getByTestId("conflict-row-c1"));
    await userEvent.click(screen.getByTestId("conflict-row-c1"));
    await userEvent.click(screen.getByTestId("resolve-keep-btn"));
    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls as [string, RequestInit | undefined][];
      const resolveCall = calls.find(([url]) => url.includes("/resolve"));
      expect(resolveCall).toBeTruthy();
      expect(JSON.parse(resolveCall![1]?.body as string).resolution).toBe("keep_old");
    });
  });

  it("defer button resolves with defer", async () => {
    render(<ConflictResolution open={true} onClose={vi.fn()} projectId="p1" />);
    await waitFor(() => screen.getByTestId("conflict-row-c1"));
    await userEvent.click(screen.getByTestId("conflict-row-c1"));
    await userEvent.click(screen.getByTestId("resolve-defer-btn"));
    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls as [string, RequestInit | undefined][];
      const resolveCall = calls.find(([url]) => url.includes("/resolve"));
      expect(resolveCall).toBeTruthy();
      expect(JSON.parse(resolveCall![1]?.body as string).resolution).toBe("defer");
    });
  });

  it("edit & merge shows textarea", async () => {
    render(<ConflictResolution open={true} onClose={vi.fn()} projectId="p1" />);
    await waitFor(() => screen.getByTestId("conflict-row-c1"));
    await userEvent.click(screen.getByTestId("conflict-row-c1"));
    await userEvent.click(screen.getByTestId("resolve-edit-btn"));
    expect(screen.getByTestId("merge-edit-textarea")).toBeInTheDocument();
  });

  it("empty state shows when no conflicts", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: async () => ({ project_id: "p1", count: 0, conflicts: [] }),
      }),
    );
    render(<ConflictResolution open={true} onClose={vi.fn()} projectId="p1" />);
    await waitFor(() => expect(screen.getByTestId("conflict-empty-state")).toBeInTheDocument());
  });

  it("close button calls onClose", async () => {
    const onClose = vi.fn();
    render(<ConflictResolution open={true} onClose={onClose} projectId="p1" />);
    await waitFor(() => screen.getByTestId("conflict-resolution-panel"));
    await userEvent.click(screen.getByTestId("conflict-panel-close-btn"));
    expect(onClose).toHaveBeenCalled();
  });
});
