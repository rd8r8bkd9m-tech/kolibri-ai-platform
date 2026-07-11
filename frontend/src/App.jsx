import "./App.css";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ControlShell } from "./control/ControlShell";
import { PublicShell } from "./shell/PublicShell";

function App() {
  const isControlRoute = globalThis.location.pathname.startsWith("/control");
  return (
    <ErrorBoundary>
      {isControlRoute ? <ControlShell /> : <PublicShell />}
    </ErrorBoundary>
  );
}

export default App;
