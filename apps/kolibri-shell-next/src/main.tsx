import { App } from "@app/App";
import { ProgramWallboard } from "@features/wallboard/ProgramWallboard";
import { createGatewayClient } from "@services/gatewayClient";
import { createProgramStatusClient } from "@services/programStatusClient";
import type { ShellClient } from "@services/shellClient";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

async function resolveClient(): Promise<ShellClient> {
  const fixtureRequested =
    import.meta.env.DEV && new URLSearchParams(window.location.search).get("fixture") === "estimate";
  if (fixtureRequested) {
    const { createEstimateFixtureClient } = await import("@dev/estimateFixture");
    return createEstimateFixtureClient(window.matchMedia("(max-width: 700px)").matches);
  }
  return createGatewayClient();
}

async function mount() {
  const root = document.getElementById("root");
  if (!root) throw new Error("Kolibri Shell root element is missing");
  if (window.location.pathname === "/wallboard") {
    createRoot(root).render(
      <StrictMode>
        <ProgramWallboard client={createProgramStatusClient()} />
      </StrictMode>,
    );
    return;
  }
  const client = await resolveClient();
  createRoot(root).render(
    <StrictMode>
      <App client={client} />
    </StrictMode>,
  );
}

void mount();
