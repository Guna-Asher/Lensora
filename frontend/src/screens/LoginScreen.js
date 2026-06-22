/**
 * LoginScreen — email/password login.
 *
 * Matches the existing app aesthetic:
 *  - bg-[#0A0A0A], max-w-md, rounded-2xl cards, #2563EB primary
 */
import React, { useState, useEffect } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { Scan, Mail, Lock } from "lucide-react";
import { supabase } from "../lib/supabaseClient";
import { useAuth } from "../context/AuthContext";

export default function LoginScreen() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Redirect if already authenticated
  useEffect(() => {
    if (user) navigate(from, { replace: true });
  }, [user, navigate, from]);

  const handleEmailLogin = async (e) => {
    e.preventDefault();
    if (!supabase) {
      setError("Authentication is not configured. Set REACT_APP_SUPABASE_URL and REACT_APP_SUPABASE_ANON_KEY.");
      return;
    }
    setLoading(true);
    setError(null);
    const { error: err } = await supabase.auth.signInWithPassword({ email, password });
    setLoading(false);
    if (err) setError(err.message);
  };

  const handleGuestMode = () => {
    localStorage.setItem("lensora_guest", "true");
    navigate(from, { replace: true });
  };

  return (
    <div
      className="flex flex-col min-h-screen bg-[#0A0A0A] px-6 py-10"
      data-testid="login-screen"
    >
      {/* Header */}
      <div className="flex flex-col items-center mb-10">
        <div className="mb-4 w-12 h-12 rounded-2xl bg-[#181818] border border-[#27272A] flex items-center justify-center">
          <Scan size={22} className="text-[#2563EB]" />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-[#F8F8F8]">
          Sign in
        </h1>
        <p className="mt-1 text-sm text-[#A1A1AA]">to continue to Lensora</p>
      </div>

      {/* Error */}
      {error && (
        <div
          data-testid="login-error"
          className="mb-5 p-4 bg-[#EF4444]/10 border border-[#EF4444]/30 rounded-2xl text-[#EF4444] text-sm text-center"
        >
          {error}
        </div>
      )}

      {/* Email form */}
      <form onSubmit={handleEmailLogin} className="space-y-3 mb-4">
        <div className="relative">
          <Mail size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#52525B]" />
          <input
            data-testid="login-email-input"
            type="email"
            placeholder="Email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full h-14 bg-[#111111] border border-[#27272A] rounded-2xl pl-11 pr-4 text-[#F8F8F8] placeholder-[#52525B] text-sm focus:outline-none focus:border-[#2563EB] transition-colors"
          />
        </div>

        <div className="relative">
          <Lock size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#52525B]" />
          <input
            data-testid="login-password-input"
            type="password"
            placeholder="Password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full h-14 bg-[#111111] border border-[#27272A] rounded-2xl pl-11 pr-4 text-[#F8F8F8] placeholder-[#52525B] text-sm focus:outline-none focus:border-[#2563EB] transition-colors"
          />
        </div>

        <button
          data-testid="login-submit-button"
          type="submit"
          disabled={loading}
          className="w-full h-14 bg-[#2563EB] text-[#F8F8F8] rounded-2xl font-medium text-sm active:opacity-80 transition-opacity disabled:opacity-50"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>

      {/* Forgot password */}
      <div className="text-right mb-8">
        <Link
          data-testid="forgot-password-link"
          to="/forgot-password"
          className="text-xs text-[#A1A1AA] hover:text-[#F8F8F8] transition-colors"
        >
          Forgot password?
        </Link>
      </div>

      {/* Register link */}
      <p className="text-center text-sm text-[#A1A1AA]">
        Don't have an account?{" "}
        <Link
          data-testid="register-link"
          to="/register"
          className="text-[#2563EB] hover:underline"
        >
          Create one
        </Link>
      </p>

      {/* Divider */}
      <div className="flex items-center gap-3 my-7">
        <div className="flex-1 h-px bg-[#27272A]" />
        <span className="text-xs text-[#3F3F46]">or</span>
        <div className="flex-1 h-px bg-[#27272A]" />
      </div>

      {/* Continue as Guest */}
      <div className="flex flex-col items-center gap-2">
        <button
          data-testid="continue-as-guest-button"
          type="button"
          onClick={handleGuestMode}
          className="w-full h-14 bg-transparent border border-[#27272A] text-[#A1A1AA] rounded-2xl font-medium text-sm hover:border-[#52525B] hover:text-[#F8F8F8] active:opacity-70 transition-colors"
        >
          Continue as Guest
        </button>
        <p data-testid="guest-scan-hint" className="text-xs text-[#3F3F46]">
          Includes 3 free analyses
        </p>
      </div>
    </div>
  );
}
