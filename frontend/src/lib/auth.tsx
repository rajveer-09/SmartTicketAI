import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, onUnauthenticated, post, refreshSession, setAccessToken } from "./api";
import type { TokenResponse, User } from "./types";

interface AuthValue {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<User>;
  completeSignUp: (email: string, code: string) => Promise<User>;
  signOut: () => Promise<void>;
  /** Exchanges the refresh cookie for a session (used after Google sign-in). */
  restore: () => Promise<User | null>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const accept = useCallback((data: TokenResponse) => {
    setAccessToken(data.access_token);
    setUser(data.user);
    return data.user;
  }, []);

  const restore = useCallback(async () => {
    // Shares one in-flight refresh, so React's double effect (and two tabs) can't
    // race and burn the rotating refresh token.
    const data = (await refreshSession()) as TokenResponse | null;
    if (!data) {
      setAccessToken(null);
      setUser(null);
      return null;
    }
    return accept(data);
  }, [accept]);

  // On load, turn an existing refresh cookie back into a session.
  useEffect(() => {
    restore().finally(() => setLoading(false));
  }, [restore]);

  useEffect(() => {
    onUnauthenticated(() => setUser(null));
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      loading,
      restore,
      signIn: async (email, password) =>
        accept(await post<TokenResponse>("/auth/login", { email, password })),
      completeSignUp: async (email, code) =>
        accept(await post<TokenResponse>("/auth/register/verify", { email, code })),
      signOut: async () => {
        try {
          await api("/auth/logout", { method: "POST", retryOn401: false });
        } finally {
          setAccessToken(null);
          setUser(null);
        }
      },
    }),
    [user, loading, accept, restore],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export const HOME_FOR_ROLE: Record<User["role"], string> = {
  user: "/tickets",
  moderator: "/moderator/tickets",
  admin: "/admin/tickets",
};
