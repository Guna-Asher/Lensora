/**
 * ProtectedRoute — redirects unauthenticated users to /login.
 *
 * While the initial session check is in-flight (loading=true) renders a
 * minimal dark spinner consistent with the app's loading overlay style.
 *
 * Preserves the intended destination in router state so LoginScreen can
 * redirect back after a successful sign-in.
 */
import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-[#0A0A0A]"
        data-testid="auth-loading"
      >
        <div className="w-8 h-8 rounded-full border-2 border-[#2563EB] border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!user) {
    const isGuest = localStorage.getItem("lensora_guest") === "true";
    if (!isGuest) {
      return (
        <Navigate to="/login" replace state={{ from: location }} />
      );
    }
  }

  return children;
}
