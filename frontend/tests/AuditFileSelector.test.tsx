import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AuditFileSelector from "../components/AuditFileSelector";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const FILE_NEW = {
  id: "1",
  filename: "test_suite_v17.xlsx",
  file_path: "./data/uploads/p1/test_suite_v17.xlsx",
  source_type: "file",
  size_bytes: 12400,
  uploaded_at: "2024-03-11T14:23:00Z",
  last_used_in_audit_id: null,
  last_used_in_audit_at: null,
  selected: true,
};

const FILE_NEW_2 = {
  id: "2",
  filename: "second_suite.csv",
  file_path: "./data/uploads/p1/second_suite.csv",
  source_type: "file",
  size_bytes: 5000,
  uploaded_at: "2024-03-12T10:00:00Z",
  last_used_in_audit_id: null,
  last_used_in_audit_at: null,
  selected: true,
};

const FILE_USED = {
  id: "3",
  filename: "old_suite.csv",
  file_path: "./data/uploads/p1/old_suite.csv",
  source_type: "file",
  size_bytes: 5000,
  uploaded_at: "2024-02-01T10:00:00Z",
  last_used_in_audit_id: "snap-123",
  last_used_in_audit_at: "2024-02-05T09:00:00Z",
  selected: false,
};

const FILE_URL = {
  id: "4",
  filename: "jira_export.csv",
  file_path: "./data/uploads/p1/jira_export.csv",
  source_type: "url",
  size_bytes: 3000,
  uploaded_at: "2024-03-10T12:00:00Z",
  last_used_in_audit_id: "snap-456",
  last_used_in_audit_at: "2024-03-10T13:00:00Z",
  selected: true,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function mockFetch(items: object[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(items),
      })
    )
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AuditFileSelector", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("test_new_files_shown_checked", async () => {
    mockFetch([FILE_NEW, FILE_NEW_2]);
    render(<AuditFileSelector projectId="p1" onSelectionChange={vi.fn()} />);

    const checkboxes = await screen.findAllByRole("checkbox");
    expect(checkboxes).toHaveLength(2);
    checkboxes.forEach((cb) => expect(cb).toBeChecked());
  });

  it("test_used_files_shown_unchecked", async () => {
    mockFetch([FILE_USED]);
    render(<AuditFileSelector projectId="p1" onSelectionChange={vi.fn()} />);

    const checkbox = await screen.findByRole("checkbox");
    expect(checkbox).not.toBeChecked();

    // Row should have reduced opacity
    const row = checkbox.parentElement as HTMLElement;
    expect(row.style.opacity).toBe("0.5");
  });

  it("test_url_source_always_checked_disabled", async () => {
    mockFetch([FILE_URL]);
    render(<AuditFileSelector projectId="p1" onSelectionChange={vi.fn()} />);

    const checkbox = await screen.findByRole("checkbox");
    expect(checkbox).toBeChecked();
    expect(checkbox).toBeDisabled();
  });

  it("test_onselection_change_called", async () => {
    const onChange = vi.fn();
    mockFetch([FILE_NEW, FILE_NEW_2]);
    render(<AuditFileSelector projectId="p1" onSelectionChange={onChange} />);

    const checkboxes = await screen.findAllByRole("checkbox");
    expect(checkboxes).toHaveLength(2);

    // Uncheck the first checkbox
    await userEvent.click(checkboxes[0]);

    // Last call should contain only the second file's path
    const lastArgs = onChange.mock.calls[onChange.mock.calls.length - 1][0] as string[];
    expect(lastArgs).toHaveLength(1);
    expect(lastArgs[0]).toBe(FILE_NEW_2.file_path);
  });
});
