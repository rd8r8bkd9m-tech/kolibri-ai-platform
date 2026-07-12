import { App } from "@app/App";
import { createGatewayClient } from "@services/gatewayClient";
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
  const client = await resolveClient();
  createRoot(root).render(
    <StrictMode>
      <App client={client} />
    </StrictMode>,
  );
}

void mount();
