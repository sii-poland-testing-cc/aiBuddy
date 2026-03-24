import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectSettingsPage from "../app/project/[projectId]/settings/page";

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useParams:  () => ({ projectId: "proj-1" }),
}));

// ── fetch helpers ─────────────────────────────────────────────────────────────

const PROJECT = { project_id: "proj-1", name: "PayFlow QA", description: "Opis testowy" };
const SETTINGS = { name: "PayFlow QA", description: "Opis testowy" };

function mockFetch(projectOk = true, settingsBody: object = SETTINGS, saveOk = true) {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      return Promise.resolve({ ok: saveOk, json: () => Promise.resolve(settingsBody) });
    }
    if ((url as string).includes("/settings")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(settingsBody) });
    }
    // project endpoint
    return Promise.resolve({
      ok: projectOk,
      json: () => Promise.resolve(PROJECT),
    });
  }));
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ProjectSettingsPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("shows loading state initially", () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    expect(screen.getByText("Ładowanie…")).toBeInTheDocument();
  });

  it("renders form with name and description loaded from settings", async () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    await waitFor(() => expect(screen.getByDisplayValue("PayFlow QA")).toBeInTheDocument());
    expect(screen.getByDisplayValue("Opis testowy")).toBeInTheDocument();
  });

  it("falls back to project row when settings are empty", async () => {
    mockFetch(true, {});
    render(<ProjectSettingsPage />);
    await waitFor(() => expect(screen.getByDisplayValue("PayFlow QA")).toBeInTheDocument());
  });

  it("shows project id in header", async () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    await waitFor(() => expect(screen.getByText("proj-1")).toBeInTheDocument());
  });

  it("shows error state when project fetch fails", async () => {
    mockFetch(false);
    render(<ProjectSettingsPage />);
    await waitFor(() => expect(screen.getByText("Nie znaleziono projektu.")).toBeInTheDocument());
  });

  it("error state shows link back to project list", async () => {
    mockFetch(false);
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByText("← Wróć do listy projektów"));
    await userEvent.click(screen.getByText("← Wróć do listy projektów"));
    expect(mockPush).toHaveBeenCalledWith("/");
  });

  it("back button navigates to project page", async () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByText("← Wróć do projektu"));
    await userEvent.click(screen.getByText("← Wróć do projektu"));
    expect(mockPush).toHaveBeenCalledWith("/project/proj-1");
  });

  it("save button is disabled when name is empty", async () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByDisplayValue("PayFlow QA"));
    await userEvent.clear(screen.getByDisplayValue("PayFlow QA"));
    expect(screen.getByRole("button", { name: /Zapisz/ })).toBeDisabled();
  });

  it("submitting form calls PUT /settings with name and description", async () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByDisplayValue("PayFlow QA"));

    const nameInput = screen.getByDisplayValue("PayFlow QA");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Nowa Nazwa");
    await userEvent.click(screen.getByRole("button", { name: /Zapisz/ }));

    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls;
      const putCall = calls.find(([, init]) => (init as RequestInit)?.method === "PUT");
      expect(putCall).toBeTruthy();
      const body = JSON.parse((putCall![1] as RequestInit).body as string);
      expect(body.name).toBe("Nowa Nazwa");
      expect(body.description).toBe("Opis testowy");
    });
  });

  it("shows 'Zapisano' confirmation after successful save", async () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByDisplayValue("PayFlow QA"));
    await userEvent.click(screen.getByRole("button", { name: /Zapisz/ }));
    await waitFor(() => expect(screen.getByText("Zapisano")).toBeInTheDocument());
  });

  it("shows error message when save fails", async () => {
    mockFetch(true, SETTINGS, false);
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByDisplayValue("PayFlow QA"));
    await userEvent.click(screen.getByRole("button", { name: /Zapisz/ }));
    await waitFor(() =>
      expect(screen.getByText("Nie udało się zapisać ustawień.")).toBeInTheDocument()
    );
  });
});
