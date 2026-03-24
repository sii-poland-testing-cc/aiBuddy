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
const SETTINGS = { name: "PayFlow QA", description: "Opis testowy", jira_url: "https://acme.atlassian.net", jira_user_email: "user@acme.com", jira_api_key: "secret-key" };

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

  it("renders jira_url and jira_api_key fields", async () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByDisplayValue("PayFlow QA"));
    expect(screen.getByPlaceholderText(/atlassian/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/API key/i)).toBeInTheDocument();
  });

  it("loads jira_url from settings", async () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByDisplayValue("https://acme.atlassian.net"));
  });

  it("test jira button is hidden when fields are empty", async () => {
    mockFetch(true, { name: "PayFlow QA", description: "" });
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByDisplayValue("PayFlow QA"));
    expect(screen.queryByText(/Testuj połączenie/)).not.toBeInTheDocument();
  });

  it("test jira button is visible when all three jira fields are filled", async () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByDisplayValue("https://acme.atlassian.net"));
    expect(screen.getByText("Testuj połączenie Jira")).toBeInTheDocument();
  });

  it("loads jira_user_email from settings", async () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByDisplayValue("user@acme.com"));
  });

  it("shows success result after successful jira test", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if ((url as string).includes("test-jira")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, detail: "Połączono jako: John" }) });
      }
      if (init?.method === "PUT") return Promise.resolve({ ok: true, json: () => Promise.resolve(SETTINGS) });
      if ((url as string).includes("/settings")) return Promise.resolve({ ok: true, json: () => Promise.resolve(SETTINGS) });
      return Promise.resolve({ ok: true, json: () => Promise.resolve(PROJECT) });
    }));
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByText("Testuj połączenie Jira"));
    await userEvent.click(screen.getByText("Testuj połączenie Jira"));
    await waitFor(() => expect(screen.getByText(/Połączono jako/)).toBeInTheDocument());
  });

  it("shows error result after failed jira test", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if ((url as string).includes("test-jira")) {
        return Promise.resolve({ ok: false, json: () => Promise.resolve({ ok: false, detail: "Nieautoryzowany. Sprawdź API key." }) });
      }
      if (init?.method === "PUT") return Promise.resolve({ ok: true, json: () => Promise.resolve(SETTINGS) });
      if ((url as string).includes("/settings")) return Promise.resolve({ ok: true, json: () => Promise.resolve(SETTINGS) });
      return Promise.resolve({ ok: true, json: () => Promise.resolve(PROJECT) });
    }));
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByText("Testuj połączenie Jira"));
    await userEvent.click(screen.getByText("Testuj połączenie Jira"));
    await waitFor(() => expect(screen.getByText(/Nieautoryzowany/)).toBeInTheDocument());
  });

  it("saves jira_url and jira_api_key in PUT payload", async () => {
    mockFetch();
    render(<ProjectSettingsPage />);
    await waitFor(() => screen.getByDisplayValue("PayFlow QA"));
    await userEvent.click(screen.getByRole("button", { name: /Zapisz/ }));
    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls;
      const putCall = calls.find(([, init]) => (init as RequestInit)?.method === "PUT");
      expect(putCall).toBeTruthy();
      const body = JSON.parse((putCall![1] as RequestInit).body as string);
      expect(body.jira_url).toBe("https://acme.atlassian.net");
      expect(body.jira_user_email).toBe("user@acme.com");
      expect(body.jira_api_key).toBe("secret-key");
    });
  });
});
