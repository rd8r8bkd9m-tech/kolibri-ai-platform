"use client";

import {
  getAccountSession,
  loginAccount,
  logoutAccount,
  registerAccount,
  updateAccountProfile,
  updateAgentProfile,
  updateModelSettings,
  type AccountUser,
  type AgentProfile,
} from "@/lib/identity/client";
import { KOLIBRI_AUTHENTICATION_REQUIRED_EVENT } from "@/lib/identity/events";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type IdentityStatus = "loading" | "anonymous" | "authenticated" | "offline";

type IdentityContextValue = {
  status: IdentityStatus;
  user: AccountUser | null;
  error: string | null;
  agentProfileSaving: boolean;
  modelSettingsSaving: boolean;
  refresh: () => Promise<void>;
  login: (input: { email: string; password: string }) => Promise<void>;
  register: (input: {
    email: string;
    name: string;
    password: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  saveProfile: (input: { name?: string }) => Promise<void>;
  setAgentProfile: (profile: AgentProfile) => Promise<void>;
  setModelSettings: (input: {
    profile: AgentProfile;
    model: string | null;
    reasoningEffort: string | null;
    serviceTier: string | null;
  }) => Promise<void>;
};

const IdentityContext = createContext<IdentityContextValue | null>(null);

function errorMessage(error: unknown) {
  return error instanceof Error && error.message.trim()
    ? error.message
    : "Новый backend Kolibri сейчас недоступен.";
}

export function IdentityProvider({
  children,
}: Readonly<{ children: ReactNode }>) {
  const [status, setStatus] = useState<IdentityStatus>("loading");
  const [user, setUser] = useState<AccountUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [agentProfileSaving, setAgentProfileSaving] = useState(false);
  const [modelSettingsSaving, setModelSettingsSaving] = useState(false);

  const applySession = useCallback(
    (session: { authenticated: boolean; user: AccountUser | null }) => {
      setUser(session.user);
      setStatus(session.authenticated ? "authenticated" : "anonymous");
      setError(null);
    },
    [],
  );

  const refresh = useCallback(async () => {
    try {
      applySession(await getAccountSession());
    } catch (requestError) {
      setUser(null);
      setStatus("offline");
      setError(errorMessage(requestError));
    }
  }, [applySession]);

  useEffect(() => {
    const controller = new AbortController();
    void getAccountSession(controller.signal)
      .then(applySession)
      .catch((requestError: unknown) => {
        if (
          requestError instanceof DOMException &&
          requestError.name === "AbortError"
        ) {
          return;
        }
        setUser(null);
        setStatus("offline");
        setError(errorMessage(requestError));
      });
    return () => controller.abort();
  }, [applySession]);

  useEffect(() => {
    const revalidate = () => {
      void refresh();
    };
    const revalidateVisibleSession = () => {
      if (document.visibilityState === "visible") revalidate();
    };

    window.addEventListener(
      KOLIBRI_AUTHENTICATION_REQUIRED_EVENT,
      revalidate,
    );
    window.addEventListener("focus", revalidate);
    document.addEventListener("visibilitychange", revalidateVisibleSession);
    return () => {
      window.removeEventListener(
        KOLIBRI_AUTHENTICATION_REQUIRED_EVENT,
        revalidate,
      );
      window.removeEventListener("focus", revalidate);
      document.removeEventListener(
        "visibilitychange",
        revalidateVisibleSession,
      );
    };
  }, [refresh]);

  const login = useCallback(
    async (input: { email: string; password: string }) => {
      applySession(await loginAccount(input));
    },
    [applySession],
  );

  const register = useCallback(
    async (input: { email: string; name: string; password: string }) => {
      applySession(await registerAccount(input));
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    await logoutAccount();
    setUser(null);
    setStatus("anonymous");
    setError(null);
  }, []);

  const saveProfile = useCallback(
    async (input: { name?: string }) => {
      const updated = await updateAccountProfile(input);
      setUser(updated);
      setStatus("authenticated");
      setError(null);
    },
    [],
  );

  const setAgentProfile = useCallback(async (profile: AgentProfile) => {
    setAgentProfileSaving(true);
    try {
      const updated = await updateAgentProfile(profile);
      setUser(updated);
      setStatus("authenticated");
      setError(null);
    } finally {
      setAgentProfileSaving(false);
    }
  }, []);

  const setModelSettings = useCallback(
    async (input: {
      profile: AgentProfile;
      model: string | null;
      reasoningEffort: string | null;
      serviceTier: string | null;
    }) => {
      setModelSettingsSaving(true);
      try {
        const updated = await updateModelSettings(input);
        setUser(updated);
        setStatus("authenticated");
        setError(null);
      } finally {
        setModelSettingsSaving(false);
      }
    },
    [],
  );

  const value = useMemo<IdentityContextValue>(
    () => ({
      status,
      user,
      error,
      agentProfileSaving,
      modelSettingsSaving,
      refresh,
      login,
      register,
      logout,
      saveProfile,
      setAgentProfile,
      setModelSettings,
    }),
    [
      error,
      agentProfileSaving,
      modelSettingsSaving,
      login,
      logout,
      refresh,
      register,
      saveProfile,
      setAgentProfile,
      setModelSettings,
      status,
      user,
    ],
  );

  return (
    <IdentityContext.Provider value={value}>
      {children}
    </IdentityContext.Provider>
  );
}

export function useIdentity() {
  const value = useContext(IdentityContext);
  if (!value) {
    throw new Error("useIdentity must be used inside IdentityProvider.");
  }
  return value;
}
