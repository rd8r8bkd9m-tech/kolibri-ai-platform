import "./App.css";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ControlShell } from "./control/ControlShell";
import { PublicShell } from "./shell/PublicShell";
import { useEffect, useState } from "react";

function App() {
  const path = (typeof window === "object" && window?.location) ? window.location.pathname : "/";
  const isControlRoute = typeof path === "string" ? path.startsWith("/control") : false;
  const isPrivateRoute = typeof path === "string" ? path.startsWith("/app") : false;
  const [isPrivateAllowed, setIsPrivateAllowed] = useState(!isPrivateRoute);
  const [isCheckingPrivateAuth, setIsCheckingPrivateAuth] = useState(isPrivateRoute);

  useEffect(() => {
    if (!isPrivateRoute) {
      return;
    }
    const check = async () => {
      try {
        const response = await fetch("/api/v1/auth/session", {
          credentials: "include",
        });
        if (response.status !== 200) {
          window.location.replace(`/login?return_url=${encodeURIComponent(window.location.pathname + window.location.search)}`);
          return;
        }
        const payload = await response.json().catch(() => ({}));
        if (!payload?.authenticated) {
          window.location.replace(`/login?return_url=${encodeURIComponent(window.location.pathname + window.location.search)}`);
          return;
        }
        setIsPrivateAllowed(true);
      } catch (error) {
        window.location.replace(`/login?return_url=${encodeURIComponent(window.location.pathname + window.location.search)}`);
      } finally {
        setIsCheckingPrivateAuth(false);
      }
    };
    check();
  }, [isPrivateRoute]);

  if (isPrivateRoute && isCheckingPrivateAuth) {
    return null;
  }
  return (
    <ErrorBoundary>
      {isPrivateRoute
        ? isPrivateAllowed
          ? <ControlShell />
          : null
        : isControlRoute
          ? <ControlShell />
          : <PublicShell />}
    </ErrorBoundary>
  );
}

export default App;
