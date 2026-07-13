import { ProgramWallboard } from "@features/wallboard/ProgramWallboard";
import type { ProgramStatusClient, ProgramStatusSnapshot } from "@services/programStatusClient";
import { ProgramStatusClientError } from "@services/programStatusClient";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

const snapshot: ProgramStatusSnapshot = {
  availability: "partial",
  sourceFreshness: "live",
  source: "program-ledger/home",
  asOf: "2026-07-13T00:17:44Z",
  observedAt: "2026-07-13T00:18:00Z",
  ageSeconds: 16,
  sourceSha256: `sha256:${"b".repeat(64)}`,
  sourceCommit: "45eef8aa3ce4a15858cf2284d31bf4da286dbc59",
  overallStatus: "in_progress",
  progress: {
    completed: 2,
    inProgress: 3,
    blocked: 3,
    notStarted: 3,
    total: 11,
    completedRatio: 0.1818,
  },
  gates: [{
    gate: 1,
    id: "gate-1",
    name: "Home development authority",
    status: "in_progress",
    blockers: ["Home Codex canary is absent"],
    nextAction: "Complete device login and run a fenced canary.",
    evidenceIds: ["home-integration:clean"],
    updatedAt: "2026-07-13T00:17:44Z",
  }],
};

function successfulClient(): ProgramStatusClient {
  return { async load() { return snapshot; } };
}

describe("Home program wallboard", () => {
  it("renders the real gate ratio, source and blockers", async () => {
    const user = userEvent.setup();
    render(<ProgramWallboard client={successfulClient()} refreshIntervalMs={60_000} />);

    expect(await screen.findByRole("heading", { name: "2 из 11 завершены" })).toBeInTheDocument();
    expect(screen.getByText("18,2%")).toBeInTheDocument();
    expect(screen.getByText("Работа продолжается")).toBeInTheDocument();
    expect(screen.getByText("Commit: 45eef8aa")).toBeInTheDocument();
    expect(screen.queryByText(/21 уз/)).not.toBeInTheDocument();

    const gate = screen.getByRole("article");
    await user.click(within(gate).getByText("1 блокирующих условия"));
    expect(within(gate).getByText("Home Codex canary is absent")).toBeInTheDocument();
  });

  it("shows an explicit owner-session blocker without zero metrics", async () => {
    const client: ProgramStatusClient = {
      async load() { throw new ProgramStatusClientError(401, "execution_api_auth_required"); },
    };
    render(<ProgramWallboard client={client} refreshIntervalMs={60_000} />);

    expect(await screen.findByRole("heading", { name: "Прогресс нельзя подтвердить" })).toBeInTheDocument();
    expect(screen.getByText("Требуется защищённая сессия владельца.")).toBeInTheDocument();
    expect(screen.queryByText(/0 из/)).not.toBeInTheDocument();
  });
});
