import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WorkContextBar from "../components/WorkContextBar";
import type { WorkContext } from "../lib/useWorkContext";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const DOMAIN: WorkContext = { id: "d1", name: "Payment Domain", level: "domain", status: "promoted", parent_id: null };
const EPIC: WorkContext   = { id: "e1", name: "Checkout Epic",  level: "epic",   status: "active",   parent_id: "d1" };
const STORY: WorkContext  = { id: "s1", name: "Happy Path",     level: "story",  status: "draft",    parent_id: "e1" };

const CONTEXTS: WorkContext[] = [DOMAIN, EPIC, STORY];

const noop = vi.fn().mockResolvedValue({});

function renderBar(props: Partial<React.ComponentProps<typeof WorkContextBar>> = {}) {
  const defaults = {
    projectId: "proj1",
    contexts: CONTEXTS,
    currentContextId: null,
    onContextChange: vi.fn(),
    createContext: noop,
    createDomain: noop,
    updateContext: noop,
    archiveContext: noop,
  };
  return render(<WorkContextBar {...defaults} {...props} />);
}

afterEach(() => { vi.clearAllMocks(); });

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("WorkContextBar", () => {
  it("renders the bar", () => {
    renderBar();
    expect(screen.getByTestId("work-context-bar")).toBeInTheDocument();
  });

  it("shows domain name at domain level (null contextId)", () => {
    renderBar({ currentContextId: null });
    expect(screen.getByTestId("breadcrumb-domain")).toHaveTextContent("Payment Domain");
  });

  it("shows Domain > Epic breadcrumb when epic selected", () => {
    renderBar({ currentContextId: "e1" });
    expect(screen.getByTestId("breadcrumb-domain")).toBeInTheDocument();
    expect(screen.getByTestId("breadcrumb-epic")).toHaveTextContent("Checkout Epic");
  });

  it("shows Domain > Epic > Story breadcrumb when story selected", () => {
    renderBar({ currentContextId: "s1" });
    expect(screen.getByTestId("breadcrumb-domain")).toBeInTheDocument();
    expect(screen.getByTestId("breadcrumb-epic")).toBeInTheDocument();
    expect(screen.getByTestId("breadcrumb-story")).toHaveTextContent("Happy Path");
  });

  it("clicking domain breadcrumb calls onContextChange(null)", async () => {
    const onChange = vi.fn();
    renderBar({ currentContextId: "e1", onContextChange: onChange });
    await userEvent.click(screen.getByTestId("breadcrumb-domain"));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("clicking epic breadcrumb calls onContextChange with epic id", async () => {
    const onChange = vi.fn();
    renderBar({ currentContextId: "s1", onContextChange: onChange });
    await userEvent.click(screen.getByTestId("breadcrumb-epic"));
    expect(onChange).toHaveBeenCalledWith("e1");
  });

  it("shows status badge for current context", () => {
    renderBar({ currentContextId: "e1" });
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("shows no status badge when at domain level (null)", () => {
    renderBar({ currentContextId: null });
    // No context selected = no status badge for the bar itself
    expect(screen.queryByText("promoted")).not.toBeInTheDocument();
  });

  it("shows 'Manage' button", () => {
    renderBar();
    expect(screen.getByTestId("manage-contexts-btn")).toBeInTheDocument();
  });

  it("clicking Manage opens the panel", async () => {
    renderBar();
    await userEvent.click(screen.getByTestId("manage-contexts-btn"));
    expect(screen.getByTestId("work-context-panel")).toBeInTheDocument();
  });

  it("panel shows context tree nodes", async () => {
    renderBar();
    await userEvent.click(screen.getByTestId("manage-contexts-btn"));
    const panel = screen.getByTestId("work-context-panel");
    expect(within(panel).getByTestId("ctx-node-d1")).toBeInTheDocument();
    expect(within(panel).getByTestId("ctx-node-e1")).toBeInTheDocument();
    expect(within(panel).getByTestId("ctx-node-s1")).toBeInTheDocument();
  });

  it("clicking a context node in panel selects it and closes panel", async () => {
    const onChange = vi.fn();
    renderBar({ onContextChange: onChange });
    await userEvent.click(screen.getByTestId("manage-contexts-btn"));
    await userEvent.click(screen.getByTestId("ctx-node-e1"));
    expect(onChange).toHaveBeenCalledWith("e1");
    expect(screen.queryByTestId("work-context-panel")).not.toBeInTheDocument();
  });

  it("panel shows + New Domain button", async () => {
    renderBar();
    await userEvent.click(screen.getByTestId("manage-contexts-btn"));
    expect(screen.getByTestId("create-domain-btn")).toBeInTheDocument();
  });

  it("clicking New Domain opens dialog", async () => {
    renderBar();
    await userEvent.click(screen.getByTestId("manage-contexts-btn"));
    await userEvent.click(screen.getByTestId("create-domain-btn"));
    expect(screen.getByTestId("ctx-dialog")).toBeInTheDocument();
    expect(screen.getByText("New Domain")).toBeInTheDocument();
  });

  it("clicking Add Epic opens create epic dialog", async () => {
    renderBar();
    await userEvent.click(screen.getByTestId("manage-contexts-btn"));
    await userEvent.click(screen.getByTestId("ctx-add-epic-d1"));
    expect(screen.getByTestId("ctx-dialog")).toBeInTheDocument();
    expect(screen.getByText(/New Epic under/)).toBeInTheDocument();
  });

  it("dialog submit calls createDomain with entered name", async () => {
    const createDomain = vi.fn().mockResolvedValue({ id: "d2", name: "New Domain", level: "domain", status: "draft", parent_id: null });
    renderBar({ createDomain });
    await userEvent.click(screen.getByTestId("manage-contexts-btn"));
    await userEvent.click(screen.getByTestId("create-domain-btn"));
    await userEvent.type(screen.getByTestId("ctx-dialog-name"), "My Domain");
    await userEvent.click(screen.getByTestId("ctx-dialog-submit"));
    expect(createDomain).toHaveBeenCalledWith("My Domain", undefined);
  });

  it("shows 'Loading…' when loading and no contexts", () => {
    renderBar({ contexts: [], loading: true });
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows 'No context' when not loading and no contexts", () => {
    renderBar({ contexts: [], loading: false });
    expect(screen.getByText("No context")).toBeInTheDocument();
  });

  it("closes panel on Escape", async () => {
    renderBar();
    await userEvent.click(screen.getByTestId("manage-contexts-btn"));
    expect(screen.getByTestId("work-context-panel")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByTestId("work-context-panel")).not.toBeInTheDocument();
  });

  // ── Lifecycle action button tests ─────────────────────────────────────────

  it("shows no lifecycle button at domain level (null contextId)", () => {
    renderBar({ currentContextId: null });
    expect(screen.queryByTestId("lifecycle-action-btn")).not.toBeInTheDocument();
  });

  it("shows 'Activate' button for draft context", () => {
    renderBar({ currentContextId: "s1" }); // STORY is draft
    const btn = screen.getByTestId("lifecycle-action-btn");
    expect(btn).toHaveTextContent("Activate");
    expect(btn).not.toBeDisabled();
  });

  it("clicking Activate calls updateContext with status active", async () => {
    const updateContext = vi.fn().mockResolvedValue({});
    renderBar({ currentContextId: "s1", updateContext });
    await userEvent.click(screen.getByTestId("lifecycle-action-btn"));
    expect(updateContext).toHaveBeenCalledWith("s1", { status: "active" });
  });

  it("shows 'Mark as Ready' button for active context", () => {
    renderBar({ currentContextId: "e1" }); // EPIC is active
    const btn = screen.getByTestId("lifecycle-action-btn");
    expect(btn).toHaveTextContent("Mark as Ready ✓");
    expect(btn).not.toBeDisabled();
  });

  it("clicking Mark as Ready calls updateContext with status ready", async () => {
    const updateContext = vi.fn().mockResolvedValue({});
    renderBar({ currentContextId: "e1", updateContext });
    await userEvent.click(screen.getByTestId("lifecycle-action-btn"));
    expect(updateContext).toHaveBeenCalledWith("e1", { status: "ready" });
  });

  it("shows enabled 'Promote ↑ to [parent]' button for ready context", () => {
    const readyEpic: WorkContext = { id: "e2", name: "Ready Epic", level: "epic", status: "ready", parent_id: "d1" };
    renderBar({ contexts: [DOMAIN, readyEpic], currentContextId: "e2" });
    const btn = screen.getByTestId("lifecycle-action-btn");
    expect(btn).toHaveTextContent("Promote ↑ to Payment Domain");
    expect(btn).not.toBeDisabled();
  });

  it("clicking Promote calls onPromote with the context", async () => {
    const onPromote = vi.fn();
    const readyEpic: WorkContext = { id: "e2", name: "Ready Epic", level: "epic", status: "ready", parent_id: "d1" };
    renderBar({ contexts: [DOMAIN, readyEpic], currentContextId: "e2", onPromote });
    await userEvent.click(screen.getByTestId("lifecycle-action-btn"));
    expect(onPromote).toHaveBeenCalledWith(readyEpic);
  });

  it("shows '✓ Promoted' label for promoted context", () => {
    const promotedEpic: WorkContext = { id: "e3", name: "Done Epic", level: "epic", status: "promoted", parent_id: "d1" };
    renderBar({ contexts: [DOMAIN, promotedEpic], currentContextId: "e3" });
    const el = screen.getByTestId("lifecycle-action-btn");
    expect(el).toHaveTextContent("✓ Promoted");
  });

  it("shows enabled 'Resolve Conflicts' button for conflict_pending context", () => {
    const conflictEpic: WorkContext = { id: "e4", name: "Conflict Epic", level: "epic", status: "conflict_pending", parent_id: "d1" };
    renderBar({ contexts: [DOMAIN, conflictEpic], currentContextId: "e4", pendingConflicts: 3 });
    const btn = screen.getByTestId("lifecycle-action-btn");
    expect(btn).toHaveTextContent("Resolve Conflicts (3)");
    expect(btn).not.toBeDisabled();
  });

  it("clicking Resolve Conflicts calls onOpenConflicts", async () => {
    const onOpenConflicts = vi.fn();
    const conflictEpic: WorkContext = { id: "e4", name: "Conflict Epic", level: "epic", status: "conflict_pending", parent_id: "d1" };
    renderBar({ contexts: [DOMAIN, conflictEpic], currentContextId: "e4", pendingConflicts: 3, onOpenConflicts });
    await userEvent.click(screen.getByTestId("lifecycle-action-btn"));
    expect(onOpenConflicts).toHaveBeenCalledTimes(1);
  });

  // ── Archive view tests ────────────────────────────────────────────────────

  it("shows 'Archive view' label when isArchiveView is true", () => {
    const promotedEpic: WorkContext = { id: "e3", name: "Done Epic", level: "epic", status: "promoted", parent_id: "d1" };
    renderBar({ contexts: [DOMAIN, promotedEpic], currentContextId: "e3", isArchiveView: true });
    expect(screen.getByTestId("archive-view-label")).toHaveTextContent("Archive view");
  });

  it("does not show 'Archive view' label when isArchiveView is false", () => {
    renderBar({ currentContextId: "e1" });
    expect(screen.queryByTestId("archive-view-label")).not.toBeInTheDocument();
  });
});
