/**
 * AuthContext — Supabase session state for the entire application.
 *
 * Provides: { user, session, loading, signOut }
 *
 * - Reads the current session once on mount via supabase.auth.getSession()
 * - Subscribes to onAuthStateChange for real-time updates (sign-in, sign-out,
 *   token refresh, password recovery)
 * - When supabase is null (env vars missing), loading is false and user is null
 *   — the app remains accessible but auth-disabled
 */
import React, { createContext, useContext, useEffect, useState } from "react";
import { supabase } from "../lib/supabaseClient";

const AuthContext = createContext({
  user: null,
  session: null,
  loading: true,
  signOut: async () => {},
});

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }

    // Hydrate from persisted session (localStorage)
    supabase.auth.getSession().then(({ data: { session: s } }) => {
      setSession(s ?? null);
      setUser(s?.user ?? null);
      setLoading(false);
    });

    // Listen for auth state changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s ?? null);
      setUser(s?.user ?? null);
    });

    return () => subscription.unsubscribe();
  }, []);

  const signOut = async () => {
    if (supabase) await supabase.auth.signOut();
  };

  return (
    <AuthContext.Provider value={{ user, session, loading, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
