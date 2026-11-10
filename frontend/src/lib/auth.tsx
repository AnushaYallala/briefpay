"use client";
/** Who is signed in. The token lives in `token.ts`; this keeps the user and memberships in React state. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import { clearToken, getToken, onTokenCleared, setToken } from "./token";
import type { Membership, User } from "./types";

type Status = "loading" | "anonymous" | "authed";
type Auth = {
  status: Status;
  user: User | null;
  memberships: Membership[];
  problem: string | null;
  login: (email: string, displayName: string) => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [problem, setProblem] = useState<string | null>(null);

  const signedOut = useCallback(() => {
    setUser(null);
    setMemberships([]);
    setStatus("anonymous");
  }, []);

  const load = useCallback(async () => {
    if (!getToken()) return signedOut();
    try {
      const me = await api<{ user: User; memberships: Membership[] }>("/auth/me");
      setUser(me.user);
      setMemberships(me.memberships);
      setProblem(null);
      setStatus("authed");
    } catch (e) {
      signedOut();
      if (e instanceof ApiError && e.isNetwork) setProblem(e.message);   // a sleeping server is not the same as being signed out
    }
  }, [signedOut]);

  useEffect(() => {
    void load();
    return onTokenCleared(signedOut);
  }, [load, signedOut]);

  const login = useCallback(async (email: string, displayName: string) => {
    const r = await api<{ token: string; user: User }>("/auth/login", { method: "POST", body: { email, display_name: displayName }, auth: false });
    setToken(r.token);
    await load();
  }, [load]);

  const logout = useCallback(() => {
    clearToken();
  }, []);

  const value = useMemo(() => ({ status, user, memberships, problem, login, logout }), [status, user, memberships, problem, login, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): Auth {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}

export function useOptionalAuth(): Auth | null {
  return useContext(Ctx);
}
