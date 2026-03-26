import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PromotionPreview from "../components/PromotionPreview";
import type { WorkContext } from "../lib/useWorkContext";

const CTX: WorkContext = {
  id: "c1",
  name: "Story 1",
  level: "story",
  status: "ready",
  parent_id: "e1",
};

const PREVIEW_RESULT = {
  promoted_count: 3,
  conflict_count: 1,
  artifact_type_summary: {
    requirement: { items_found: 4, promoted: 3, conflicts: 1 },
    graph_node: { items_found: 0, promoted: 0, conflicts: 0 },
    graph_edge: { items_found: 0, promoted: 0, conflicts: 0 },
    glossary_term: { items_found: 0, promoted: 0, conflicts: 0 },
  },
};

describe("PromotionPreview", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/promote")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ ...PREVIEW_RESULT, conflict_count: 0 }),
          });
        }
        return Promise.resolve({ ok: true, json: async () => PREVIEW_RESULT });
      }),
    );
  });
  afterEach(() => { vi.restoreAllMocks(); });

  it("renders the dialog", async () => {
    render(
      <PromotionPreview
        projectId="p1"
        context={CTX}
        parentName="Epic A"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId("promotion-preview-dialog")).toBeInTheDocument();
  });

  it("shows context name and parent name", async () => {
    render(
      <PromotionPreview
        projectId="p1"
        context={CTX}
        parentName="Epic A"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText(/Story 1/)).toBeInTheDocument();
    expect(screen.getByText(/Epic A/)).toBeInTheDocument();
  });

  it("shows clean items count after preview loads", async () => {
    render(
      <PromotionPreview
        projectId="p1"
        context={CTX}
        parentName="Epic A"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    await waitFor(() => expect(screen.getByText(/Ready to promote: 3/)).toBeInTheDocument());
  });

  it("shows conflicts section when conflicts exist", async () => {
    render(
      <PromotionPreview
        projectId="p1"
        context={CTX}
        parentName="Epic A"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    await waitFor(() => expect(screen.getByText(/Conflicts detected: 1/)).toBeInTheDocument());
  });

  it("promote button shows 'Promote Clean' when conflicts", async () => {
    render(
      <PromotionPreview
        projectId="p1"
        context={CTX}
        parentName="Epic A"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("promotion-confirm-btn")).toHaveTextContent(/Promote Clean/),
    );
  });

  it("cancel button calls onCancel", async () => {
    const onCancel = vi.fn();
    render(
      <PromotionPreview
        projectId="p1"
        context={CTX}
        parentName="Epic A"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );
    await userEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("clicking promote calls onConfirm with result", async () => {
    const onConfirm = vi.fn();
    render(
      <PromotionPreview
        projectId="p1"
        context={CTX}
        parentName="Epic A"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    await waitFor(() => screen.getByTestId("promotion-confirm-btn"));
    await userEvent.click(screen.getByTestId("promotion-confirm-btn"));
    await waitFor(() => expect(onConfirm).toHaveBeenCalled());
  });
});
